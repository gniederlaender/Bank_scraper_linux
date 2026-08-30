#!/usr/bin/env python3
"""
Generate HTML page with interactive Plotly charts for housing loan data from durchblicker.at
"""

import sqlite3
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import json
import base64
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from db_helper import get_all_loan_offers, get_latest_oenb_table_data
from competitor_trend_charts import (
    generate_competitor_sollzins_chart,
    generate_competitor_effektivzins_chart,
    generate_static_png_competitor_sollzins,
    generate_static_png_competitor_effektivzins
)
import glob

# Try to load dotenv if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not available, will use environment variables

# Get paths from environment or use relative paths
BASE_DIR = Path(os.getenv('BANKCOMPARISON_BASE_DIR', '.'))
DB_PATH = BASE_DIR / os.getenv('HOUSING_LOAN_DB_PATH', 'austrian_banks_housing_loan.db')
HTML_PATH = BASE_DIR / os.getenv('HOUSING_LOAN_HTML_PATH', 'bank_comparison_housing_loan_durchblicker.html')
HTML_EMAIL_PATH = BASE_DIR / os.getenv('HOUSING_LOAN_EMAIL_HTML_PATH', 'bank_comparison_housing_loan_durchblicker_email.html')
CHART_PNG_PATH = BASE_DIR / os.getenv('HOUSING_LOAN_CHART_PNG_PATH', 'housing_loan_chart.png')
INDIVIDUAL_OFFERS_CHART_PNG_PATH = BASE_DIR / os.getenv('INDIVIDUAL_OFFERS_CHART_PNG_PATH', 'individual_offers_chart.png')
SCREENSHOTS_DIR = BASE_DIR / 'screenshots'

# URL the "Angebot erfassen" form on the web report submits to. Defaults to a
# same-origin relative path so it works wherever the report is hosted, via an
# Apache/nginx reverse proxy in front of offer_api.py (see README). A
# hardcoded http://localhost:5001 only ever works when the *viewer's own
# machine* runs the API, which is never true for a page served from a domain.
OFFER_API_URL = os.getenv('OFFER_API_URL', '/bankapi/offers')

# Shared design tokens for Plotly charts, kept in sync with the CSS custom
# properties in generate_html()'s <style> block so charts and page chrome match.
PLOTLY_FONT = '-apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif'
COLOR_TEXT = '#1b2733'
COLOR_TEXT_MUTED = '#5b6b78'
COLOR_GRID = '#e2e8ee'
COLOR_ACCENT = '#0a8a9a'
COLOR_PRIMARY = '#0f3b52'
COLOR_TREND_UP = '#c0392b'    # rate increase - worse for borrowers
COLOR_TREND_DOWN = '#1e8449'  # rate decrease - better for borrowers
COLOR_TREND_FLAT = '#7f8c8d'

# Modern, distinguishable per-Fixlaufzeit palette for the Durchblicker chart,
# shared between the interactive Plotly version and the static email PNG.
FIXIERUNG_COLORS = {
    0: '#2563eb',   # Blue
    5: '#059669',   # Emerald
    10: '#d97706',  # Amber
    15: '#dc2626',  # Red
    20: '#7c3aed',  # Violet
    25: '#0891b2',  # Cyan
    30: '#db2777'   # Pink
}


def parse_percent_string(value: Optional[str]) -> Optional[float]:
    """
    Parse a German-formatted rate string like '3,490 % p.a.' into 3.49.
    Returns None if value is missing or unparseable.
    """
    if not value:
        return None
    match = re.match(r'\s*(-?[\d.,]+)', value)
    if not match:
        return None
    try:
        return float(match.group(1).replace('.', '').replace(',', '.'))
    except ValueError:
        return None


def format_percent_short(value: Optional[float]) -> str:
    """Format a parsed rate as a compact '3,320%' string (no ' p.a.' suffix etc.)."""
    if value is None:
        return '–'
    return f'{value:.3f}'.replace('.', ',') + '%'


def parse_scrape_date(value) -> Optional[datetime]:
    """Parse a scraping_runs.scrape_date value (datetime or sqlite string) into a datetime."""
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    text = str(value).strip()
    for fmt in ('%Y-%m-%dT%H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S',
                '%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def find_previous_run(sorted_runs, min_gap_days: int = 6):
    """
    Find the most recent run at least `min_gap_days` before the latest run in
    `sorted_runs` (already sorted by scrape_date descending, each item shaped
    like {'run': {...}, 'variations': [...]}).

    The pipeline normally runs weekly (Mondays), so the trend table should
    compare week-over-week. Just taking "the second most recent run" breaks
    this whenever the pipeline runs more than once in the same week (e.g.
    while testing) - it would then compare against a run from hours ago
    instead of the previous week, making the trend meaningless.

    Additionally, the candidate run must have valid data (zinssatz != '-')
    to be usable for trend comparison. Runs with invalid/placeholder data
    are skipped.

    Returns None if there's no run far enough in the past yet.
    """
    if len(sorted_runs) < 2:
        return None

    latest_date = parse_scrape_date(sorted_runs[0]['run']['scrape_date'])
    if latest_date is None:
        # Can't determine the gap reliably; fall back to the immediately
        # preceding run rather than showing no trend at all.
        return sorted_runs[1]

    for candidate in sorted_runs[1:]:
        candidate_date = parse_scrape_date(candidate['run']['scrape_date'])
        if candidate_date is None:
            continue
        if (latest_date - candidate_date).days >= min_gap_days:
            # Check if this candidate has valid data (not all zinssatz = '-')
            variations = candidate.get('variations', [])
            if not variations:
                continue

            # Count how many variations have valid zinssatz (not '-')
            valid_count = sum(
                1 for v in variations
                if v.get('zinssatz') and v.get('zinssatz') != '-'
            )

            # Only return this candidate if it has at least some valid data
            if valid_count > 0:
                return candidate

    return None


def compute_trend_rows(variations, previous_variations):
    """
    Build trend rows comparing each Fixlaufzeit's Sollzins between the
    previous and current scraping run, for the trend table under the
    Durchblicker chart.

    Args:
        variations: list of variation dicts for the current/latest run
        previous_variations: list of variation dicts for the previous run
            of the same Laufzeit, or None if there is no earlier run yet

    Returns:
        List of dicts sorted by fixierung_jahre:
        {'fixierung_jahre', 'current_str', 'previous_str', 'trend'}
        where trend is one of 'up', 'down', 'flat', 'na'.
    """
    previous_by_fixierung = {}
    if previous_variations:
        for v in previous_variations:
            previous_by_fixierung[v['fixierung_jahre']] = v.get('zinssatz')

    rows = []
    for v in sorted(variations, key=lambda x: x['fixierung_jahre']):
        fixierung = v['fixierung_jahre']
        current_str = v.get('zinssatz')
        previous_str = previous_by_fixierung.get(fixierung)

        current_val = parse_percent_string(current_str)
        previous_val = parse_percent_string(previous_str)

        if current_val is None or previous_val is None:
            trend = 'na'
        elif abs(current_val - previous_val) < 0.005:
            trend = 'flat'
        elif current_val > previous_val:
            trend = 'up'
        else:
            trend = 'down'

        rows.append({
            'fixierung_jahre': fixierung,
            'current_str': current_str,
            'previous_str': previous_str,
            'current_short': format_percent_short(current_val),
            'previous_short': format_percent_short(previous_val),
            'trend': trend
        })

    return rows


def trend_badge_html(trend: str) -> str:
    """Render the arrow+color badge for one trend table row."""
    if trend == 'up':
        return f'<span style="color:{COLOR_TREND_UP}; font-weight:700;">▲ Anstieg</span>'
    elif trend == 'down':
        return f'<span style="color:{COLOR_TREND_DOWN}; font-weight:700;">▼ Rückgang</span>'
    elif trend == 'flat':
        return f'<span style="color:{COLOR_TREND_FLAT}; font-weight:700;">▬ Unverändert</span>'
    else:
        return f'<span style="color:{COLOR_TREND_FLAT};">–</span>'


def get_bank_color(anbieter: str) -> str:
    """
    Get color for a bank based on its name.
    
    Color scheme:
    - Bank Austria / UniCredit - red
    - Volksbank - blue
    - Raiffeisen - yellow
    - Sparkasse (any) - light blue
    - Others - any color from palette
    """
    anbieter_lower = anbieter.lower()

    # Specific bank colors - modern, muted-saturated palette instead of pure RGB
    if 'bank austria' in anbieter_lower or 'unicredit' in anbieter_lower:
        return '#dc2626'  # Red
    elif 'volksbank' in anbieter_lower:
        return '#2563eb'  # Blue
    elif 'raiffeisen' in anbieter_lower:
        return '#eab308'  # Yellow/gold
    elif 'sparkasse' in anbieter_lower:
        return '#0ea5e9'  # Sky blue - for all Sparkasse banks

    # Default colors for other banks
    default_colors = [
        '#f97316',  # Orange
        '#ec4899',  # Pink
        '#84cc16',  # Lime green
        '#7c3aed',  # Violet
        '#0d9488',  # Teal
        '#f43f5e',  # Rose
        '#6366f1',  # Indigo
        '#ca8a04',  # Gold
    ]
    
    # Use hash of bank name to consistently assign colors
    hash_value = hash(anbieter) % len(default_colors)
    return default_colors[hash_value]


def generate_interactive_chart():
    """
    Generate interactive Plotly chart with:
    - Laufzeit dropdown filter (All, 15, 20, 25, 30 Jahre)
    - Checkboxes for Zinssatz and Effektiver Zinssatz
    - Interactive legend, zoom, pan, hover
    """
    conn = sqlite3.connect(DB_PATH)
    
    # Query data from the view
    query = """
    SELECT 
        run_id,
        fixierung_jahre,
        run_scrape_date as scrape_timestamp,
        zinssatz_numeric,
        effektiver_zinssatz_numeric,
        zinssatz,
        effektiver_zinssatz,
        run_kreditbetrag,
        run_laufzeit_jahre
    FROM housing_loan_chart_ready
    ORDER BY run_scrape_date, fixierung_jahre
    """
    
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    if df.empty:
        print("[WARN] No data available for chart generation")
        return None, []
    
    # Convert timestamp to datetime. format='mixed' guards against rows
    # written with inconsistent separators crashing the whole report.
    df['scrape_timestamp'] = pd.to_datetime(df['scrape_timestamp'], format='mixed')
    
    # Colors for each Fixierung variation (years)
    colors = FIXIERUNG_COLORS

    # Get unique Fixierung and Laufzeit values
    fixierung_values = sorted(df['fixierung_jahre'].unique())
    laufzeit_values = sorted(df['run_laufzeit_jahre'].unique())
    
    print(f"Creating interactive chart with {len(fixierung_values)} Fixierung variations "
          f"and {len(laufzeit_values)} Laufzeit options...")
    
    # Create figure
    fig = go.Figure()
    
    # Add traces for each Fixierung and Laufzeit combination
    for laufzeit in laufzeit_values:
        for fixierung in fixierung_values:
            # Filter data for this combination
            mask = (df['fixierung_jahre'] == fixierung) & (df['run_laufzeit_jahre'] == laufzeit)
            data = df[mask].copy()
            
            if data.empty:
                continue
            
            data = data.sort_values('scrape_timestamp')
            color = colors.get(fixierung, '#333333')
            
            # Trace for Sollzins (solid line)
            fig.add_trace(go.Scatter(
                x=data['scrape_timestamp'],
                y=data['zinssatz_numeric'],
                mode='lines+markers',
                name=f'{fixierung}J fix - {laufzeit}J SollZ',
                line=dict(color=color, width=3, dash='solid'),
                marker=dict(size=9, symbol='circle', line=dict(width=1, color='white')),
                legendgroup=f'fixierung_{fixierung}_laufzeit_{laufzeit}',
                hovertemplate=(
                    f'<b>Fixlaufzeit: {fixierung} Jahre</b><br>'
                    f'Laufzeit: {laufzeit} Jahre<br>'
                    'Datum: %{x|%d.%m.%Y}<br>'
                    'Sollzins: %{y:.3f}%<br>'
                    '<extra></extra>'
                ),
                visible=True,  # All visible by default
                customdata=[[laufzeit, 'zinssatz', fixierung]] * len(data)
            ))

            # Trace for Effektiver Zinssatz (dashed line)
            fig.add_trace(go.Scatter(
                x=data['scrape_timestamp'],
                y=data['effektiver_zinssatz_numeric'],
                mode='lines+markers',
                name=f'{fixierung}J fix - {laufzeit}J EffZ',
                line=dict(color=color, width=2.5, dash='dash'),
                marker=dict(size=8, symbol='square', line=dict(width=1, color='white')),
                legendgroup=f'fixierung_{fixierung}_laufzeit_{laufzeit}',
                hovertemplate=(
                    f'<b>Fixlaufzeit: {fixierung} Jahre</b><br>'
                    f'Laufzeit: {laufzeit} Jahre<br>'
                    'Datum: %{x|%d.%m.%Y}<br>'
                    'Eff. Zinssatz: %{y:.3f}%<br>'
                    '<extra></extra>'
                ),
                visible=True,  # All visible by default
                customdata=[[laufzeit, 'effektiver', fixierung]] * len(data)
            ))
    
    # We'll use custom HTML controls instead of Plotly updatemenus for combined filtering
    # Store trace metadata for JavaScript filtering
    trace_metadata = []
    for trace in fig.data:
        if trace.customdata:
            trace_metadata.append({
                'laufzeit': trace.customdata[0][0],
                'type': trace.customdata[0][1],
                'fixierung': trace.customdata[0][2]
            })
        else:
            trace_metadata.append({'laufzeit': None, 'type': None, 'fixierung': None})
    
    # Update layout (no updatemenus - we'll use custom HTML controls; the chart
    # title lives in the surrounding HTML card header, not inside the plot)
    fig.update_layout(
        xaxis=dict(
            title=dict(text='Datum', font=dict(size=14, family=PLOTLY_FONT, color=COLOR_TEXT_MUTED)),
            tickfont=dict(color=COLOR_TEXT_MUTED, size=12),
            showgrid=True,
            gridwidth=1,
            gridcolor=COLOR_GRID,
            tickformat='%d.%m.%Y'
        ),
        yaxis=dict(
            title=dict(text='Sollzins (%)', font=dict(size=14, family=PLOTLY_FONT, color=COLOR_TEXT_MUTED)),
            tickfont=dict(color=COLOR_TEXT_MUTED, size=12),
            showgrid=True,
            gridwidth=1,
            gridcolor=COLOR_GRID
        ),
        hovermode='closest',
        hoverlabel=dict(font=dict(family=PLOTLY_FONT, size=13, color=COLOR_TEXT), bgcolor='white', bordercolor=COLOR_GRID),
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        font=dict(family=PLOTLY_FONT, size=13, color=COLOR_TEXT),
        legend=dict(
            orientation="v",
            yanchor="top",
            y=1,
            xanchor="left",
            x=1.02,
            bgcolor="rgba(255,255,255,0.9)",
            bordercolor=COLOR_GRID,
            borderwidth=1,
            font=dict(size=12)
        ),
        height=600,
        margin=dict(l=70, r=260, t=20, b=60)
    )
    
    # Convert to HTML
    chart_html = fig.to_html(
        include_plotlyjs='cdn',
        div_id='plotly-chart',
        config={
            'displayModeBar': True,
            'displaylogo': False,
            'modeBarButtonsToRemove': ['select2d', 'lasso2d'],
            'toImageButtonOptions': {
                'format': 'png',
                'filename': 'housing_loan_chart',
                'height': 800,
                'width': 1400,
                'scale': 2
            },
            'responsive': True
        }
    )
    
    # Export chart as static PNG for email embedding using matplotlib
    print("Exporting chart as PNG for email (using matplotlib)...")
    try:
        png_base64 = generate_static_png_chart(df, fixierung_values, laufzeit_values, colors)
        print(f"[OK] Chart PNG saved: {CHART_PNG_PATH}")
    except Exception as e:
        print(f"[WARN] Warning: Could not export PNG: {e}")
        print("   (Email version will be generated without chart)")
        png_base64 = None
    
    return chart_html, laufzeit_values, fixierung_values, trace_metadata, png_base64


def compute_lowest_offers_last_30_days(user_offers, days: int = 30):
    """
    For each bank that submitted at least one competitor offer within the
    last `days` days, find its lowest Fixzins (Sollzins) offer in that
    window, along with the Fixlaufzeit and date it was quoted at.

    Returns a list of dicts sorted by rate ascending (best offer first):
    {'anbieter', 'fixzinssatz', 'fixzinssatz_in_jahren_display', 'angebotsdatum'}
    """
    cutoff = datetime.now() - timedelta(days=days)
    recent = [
        o for o in user_offers
        if o.get('angebotsdatum') and o['angebotsdatum'] >= cutoff and o.get('fixzinssatz') is not None
    ]

    best_by_bank = {}
    for offer in recent:
        anbieter = offer['anbieter']
        current_best = best_by_bank.get(anbieter)
        if current_best is None or offer['fixzinssatz'] < current_best['fixzinssatz']:
            best_by_bank[anbieter] = offer

    rows = [
        {
            'anbieter': anbieter,
            'fixzinssatz': offer['fixzinssatz'],
            'fixzinssatz_in_jahren_display': offer.get('fixzinssatz_in_jahren_display') or 'n/a',
            'angebotsdatum': offer['angebotsdatum'],
        }
        for anbieter, offer in best_by_bank.items()
    ]
    rows.sort(key=lambda r: r['fixzinssatz'])
    return rows


def generate_lowest_offers_table_html(user_offers, days: int = 30) -> str:
    """Render the 'lowest Sollzins per bank in the last N days' table HTML."""
    rows = compute_lowest_offers_last_30_days(user_offers, days=days)
    if not rows:
        return (
            f'<p style="text-align: center; color: var(--color-text-muted); padding: 20px;">'
            f'Keine Konkurrenzangebote in den letzten {days} Tagen</p>'
        )

    body_rows = ''.join(
        f'''
                        <tr>
                            <td class="fixierung-cell">{row['anbieter']}</td>
                            <td class="rate-cell">{format_percent_short(row['fixzinssatz'])}</td>
                            <td>{row['fixzinssatz_in_jahren_display']}</td>
                            <td>{row['angebotsdatum'].strftime('%d.%m.%Y')}</td>
                        </tr>'''
        for row in rows
    )

    return f'''
            <div class="table-container" style="margin-top: 24px;">
                <h2 style="margin-bottom: 16px;">🏆 Niedrigster Sollzins je Bank (letzte {days} Tage)</h2>
                <table>
                    <thead>
                        <tr>
                            <th>Bank</th>
                            <th>Niedrigster Sollzins</th>
                            <th>Fixlaufzeit</th>
                            <th>Datum</th>
                        </tr>
                    </thead>
                    <tbody>{body_rows}
                    </tbody>
                </table>
            </div>'''


def generate_competitor_trend_charts_html(
    sollzins_chart_html,
    sollzins_fixierung_values,
    sollzins_table_html,
    effektivzins_chart_html,
    effektivzins_fixierung_values,
    effektivzins_table_html,
    lowest_offers_table_html
):
    """
    Generate HTML for the two new competitor trend charts (Sollzins and Effektivzins).
    Replaces the old individual offers chart.
    """
    return f'''
        <!-- Sollzinssatz Trend Chart (NEW) -->
        <div class="chart-container" style="margin-top: 40px;">
            <div class="chart-title">📊 Sollzinssatz Konkurrenzangebote - Zeitverlauf</div>
            <details class="filters-accordion">
                <summary>🔧 Filter</summary>
                <div class="accordion-body">
                <div class="chart-controls">
                <div class="control-group">
                    <span class="control-label">Fixlaufzeit:</span>
                    <select id="sollzins-fixierung-filter">
                        <option value="all">Alle Fixlaufzeiten</option>
{''.join([f'                        <option value="{fx}"{"selected" if fx == 10 else ""}>{fx} Jahre</option>\n' for fx in sollzins_fixierung_values])}                    </select>
                </div>
                </div>
                </div>
            </details>

            {sollzins_chart_html if sollzins_chart_html else '<p style="text-align: center; color: var(--color-text-muted); padding: 40px;">Keine Daten verfügbar</p>'}

            <script>
                // Filter logic for Sollzins chart
                function applySollzinsFilter() {{
                    const chartDiv = document.getElementById('plotly-competitor-sollzins-chart');
                    if (!chartDiv || !chartDiv.data) return;

                    const filterValue = document.getElementById('sollzins-fixierung-filter').value;
                    const visible = [];

                    for (let i = 0; i < chartDiv.data.length; i++) {{
                        const trace = chartDiv.data[i];
                        if (!trace.customdata || trace.customdata.length === 0) {{
                            visible.push(true);
                            continue;
                        }}

                        const fixierung = trace.customdata[0][0];
                        if (filterValue === 'all') {{
                            visible.push(true);
                        }} else {{
                            visible.push(fixierung === parseInt(filterValue));
                        }}
                    }}

                    Plotly.restyle('plotly-competitor-sollzins-chart', {{'visible': visible}});
                }}

                if (document.getElementById('sollzins-fixierung-filter')) {{
                    document.getElementById('sollzins-fixierung-filter').addEventListener('change', applySollzinsFilter);
                }}

                setTimeout(() => {{
                    applySollzinsFilter();
                }}, 1500);
            </script>
{sollzins_table_html}
        </div>

        <!-- Effektivzinssatz Trend Chart (NEW) -->
        <div class="chart-container" style="margin-top: 40px;">
            <div class="chart-title">📈 Effektivzinssatz Konkurrenzangebote - Zeitverlauf</div>
            <details class="filters-accordion">
                <summary>🔧 Filter</summary>
                <div class="accordion-body">
                <div class="chart-controls">
                <div class="control-group">
                    <span class="control-label">Fixlaufzeit:</span>
                    <select id="effektivzins-fixierung-filter">
                        <option value="all">Alle Fixlaufzeiten</option>
{''.join([f'                        <option value="{fx}"{"selected" if fx == 10 else ""}>{fx} Jahre</option>\n' for fx in effektivzins_fixierung_values])}                    </select>
                </div>
                </div>
                </div>
            </details>

            {effektivzins_chart_html if effektivzins_chart_html else '<p style="text-align: center; color: var(--color-text-muted); padding: 40px;">Keine Daten verfügbar</p>'}

            <script>
                // Filter logic for Effektivzins chart
                function applyEffektivzinsFilter() {{
                    const chartDiv = document.getElementById('plotly-competitor-effektivzins-chart');
                    if (!chartDiv || !chartDiv.data) return;

                    const filterValue = document.getElementById('effektivzins-fixierung-filter').value;
                    const visible = [];

                    for (let i = 0; i < chartDiv.data.length; i++) {{
                        const trace = chartDiv.data[i];
                        if (!trace.customdata || trace.customdata.length === 0) {{
                            visible.push(true);
                            continue;
                        }}

                        const fixierung = trace.customdata[0][0];
                        if (filterValue === 'all') {{
                            visible.push(true);
                        }} else {{
                            visible.push(fixierung === parseInt(filterValue));
                        }}
                    }}

                    Plotly.restyle('plotly-competitor-effektivzins-chart', {{'visible': visible}});
                }}

                if (document.getElementById('effektivzins-fixierung-filter')) {{
                    document.getElementById('effektivzins-fixierung-filter').addEventListener('change', applyEffektivzinsFilter);
                }}

                setTimeout(() => {{
                    applyEffektivzinsFilter();
                }}, 1500);
            </script>
{effektivzins_table_html}
{lowest_offers_table_html}
        </div>
'''


def generate_individual_offers_chart():
    """
    Generate interactive Plotly chart with ONLY individual loan offers.
    
    Features:
    - Color coding by bank/competitor (not fixierung)
    - Same filters: Laufzeit, Fixierung, Zinssatz type
    - Interactive legend, zoom, pan, hover
    """
    # Get all individual offers
    try:
        user_offers = get_all_loan_offers()
        
        if not user_offers:
            print("[WARN] No individual offers found in database")
            return None, [], [], []
        
        print(f"[INFO] Found {len(user_offers)} individual offers")
                
    except Exception as e:
        print(f"[ERROR] Could not retrieve individual offers: {e}")
        return None, [], [], []
    
    # Get unique values for filters
    laufzeit_values = sorted(set(
        offer.get('laufzeit_numeric') 
        for offer in user_offers 
        if offer.get('laufzeit_numeric') is not None
    ))
    
    fixierung_values = sorted(set(
        offer.get('fixzinssatz_in_jahren_numeric')
        for offer in user_offers
        if offer.get('fixzinssatz_in_jahren_numeric') is not None
    ))
    
    print(f"[INFO] Individual offers - Laufzeit values: {laufzeit_values}")
    print(f"[INFO] Individual offers - Fixierung values: {fixierung_values}")
            
    # Create figure
    fig = go.Figure()

    # Group offers by bank for consistent coloring
    bank_colors = {}

    # Add traces for each offer - one point per offer, no connecting lines.
    # (A per-bank connected-line version was tried and reverted: it read as
    # a trend chart when the actual ask is "what did each bank quote, when,
    # at what Fixlaufzeit" - the last-30-days table below covers that.)
    for offer in user_offers:
        anbieter = offer['anbieter']
        date = offer['angebotsdatum']
        laufzeit_numeric = offer.get('laufzeit_numeric')
        fixzins_years = offer.get('fixzinssatz_in_jahren_numeric')
        fixzins_display = offer.get('fixzinssatz_in_jahren_display') or "n/a"

        # Get or assign color for this bank
        if anbieter not in bank_colors:
            bank_colors[anbieter] = get_bank_color(anbieter)
        color = bank_colors[anbieter]

        # Trace for Fixzins (star marker)
        fig.add_trace(go.Scatter(
            x=[date],
            y=[offer['fixzinssatz']],
            mode='markers',
            name=f'{anbieter} - Fixzins',
            line=dict(color=color, width=2),
            marker=dict(
                size=16,
                symbol='star',
                color=color,
                opacity=0.9,
                line=dict(width=1.5, color=COLOR_PRIMARY)
            ),
            legendgroup=anbieter,
            hovertemplate=(
                f'<b>{anbieter}</b><br>'
                'Datum: %{x|%d.%m.%Y}<br>'
                f'Fixzins: {offer["fixzinssatz"]:.3f}%<br>'
                f'Eff. Zins: {offer["effektivzinssatz"]:.3f}%<br>'
                f'Laufzeit: {offer.get("laufzeit", "N/A")}<br>'
                f'Fixzinsperiode: {fixzins_display}<br>'
                '<extra></extra>'
            ),
            visible=True,  # Visible by default
            customdata=[[laufzeit_numeric, 'user_offer_fix', fixzins_years, anbieter]]
        ))

        # Trace for Effektivzinssatz (diamond marker)
        fig.add_trace(go.Scatter(
            x=[date],
            y=[offer['effektivzinssatz']],
            mode='markers',
            name=f'{anbieter} - Eff. Zins',
            line=dict(color=color, width=2, dash='dash'),
            marker=dict(
                size=13,
                symbol='diamond',
                color=color,
                opacity=0.9,
                line=dict(width=1.5, color=COLOR_PRIMARY)
            ),
            legendgroup=anbieter,
            hovertemplate=(
                f'<b>{anbieter}</b><br>'
                'Datum: %{x|%d.%m.%Y}<br>'
                f'Fixzins: {offer["fixzinssatz"]:.3f}%<br>'
                f'Eff. Zins: {offer["effektivzinssatz"]:.3f}%<br>'
                f'Laufzeit: {offer.get("laufzeit", "N/A")}<br>'
                f'Fixzinsperiode: {fixzins_display}<br>'
                '<extra></extra>'
            ),
            visible=True,  # Visible by default
            customdata=[[laufzeit_numeric, 'user_offer_eff', fixzins_years, anbieter]]
        ))
                
    # Store trace metadata for JavaScript filtering
    trace_metadata = []
    for trace in fig.data:
        if trace.customdata:
            trace_metadata.append({
                'laufzeit': trace.customdata[0][0],
                'type': trace.customdata[0][1],
                'fixierung': trace.customdata[0][2],
                'anbieter': trace.customdata[0][3] if len(trace.customdata[0]) > 3 else None
            })
        else:
            trace_metadata.append({'laufzeit': None, 'type': None, 'fixierung': None, 'anbieter': None})
    
    # Update layout (title lives in the surrounding HTML card header)
    fig.update_layout(
        xaxis=dict(
            title=dict(text='Datum', font=dict(size=14, family=PLOTLY_FONT, color=COLOR_TEXT_MUTED)),
            tickfont=dict(color=COLOR_TEXT_MUTED, size=12),
            showgrid=True,
            gridwidth=1,
            gridcolor=COLOR_GRID,
            tickformat='%d.%m.%Y'
        ),
        yaxis=dict(
            title=dict(text='Sollzins (%)', font=dict(size=14, family=PLOTLY_FONT, color=COLOR_TEXT_MUTED)),
            tickfont=dict(color=COLOR_TEXT_MUTED, size=12),
            showgrid=True,
            gridwidth=1,
            gridcolor=COLOR_GRID
        ),
        hovermode='closest',
        hoverlabel=dict(font=dict(family=PLOTLY_FONT, size=13, color=COLOR_TEXT), bgcolor='white', bordercolor=COLOR_GRID),
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        font=dict(family=PLOTLY_FONT, size=13, color=COLOR_TEXT),
        legend=dict(
            orientation="v",
            yanchor="top",
            y=1,
            xanchor="left",
            x=1.02,
            bgcolor="rgba(255,255,255,0.9)",
            bordercolor=COLOR_GRID,
            borderwidth=1,
            font=dict(size=12)
        ),
        height=600,
        margin=dict(l=70, r=260, t=20, b=60)
    )

    # Convert to HTML
    chart_html = fig.to_html(
        include_plotlyjs='cdn',
        div_id='plotly-individual-offers-chart',
        config={
            'displayModeBar': True,
            'displaylogo': False,
            'modeBarButtonsToRemove': ['select2d', 'lasso2d'],
            'toImageButtonOptions': {
                'format': 'png',
                'filename': 'individual_offers_chart',
                'height': 800,
                'width': 1400,
                'scale': 2
            },
            'responsive': True
        }
    )
    
    # Export chart as static PNG for email embedding using matplotlib
    print("Exporting individual offers chart as PNG for email (using matplotlib)...")
    try:
        png_base64 = generate_static_png_individual_offers(user_offers, bank_colors)
        print(f"[OK] Individual offers chart PNG saved: {INDIVIDUAL_OFFERS_CHART_PNG_PATH}")
    except Exception as e:
        print(f"[WARN] Warning: Could not export individual offers PNG: {e}")
        print("   (Email version will be generated without individual offers chart)")
        png_base64 = None
    
    return chart_html, laufzeit_values, fixierung_values, trace_metadata, png_base64


def generate_static_png_individual_offers(user_offers, bank_colors):
    """Generate static PNG chart using matplotlib for individual offers email embedding - Default: Eff. Zinssatz only, last 12 months"""

    from datetime import timedelta

    # Filter to last 12 months
    twelve_months_ago = datetime.now() - timedelta(days=365)
    filtered_offers = [
        offer for offer in user_offers
        if offer.get('angebotsdatum') and offer['angebotsdatum'] >= twelve_months_ago
    ]

    if not filtered_offers:
        print("[WARN] No individual offers in last 12 months, using all available data")
        filtered_offers = user_offers

    # Create figure
    plt.figure(figsize=(14, 7))

    # Group offers by bank
    offers_by_bank = {}
    for offer in filtered_offers:
        anbieter = offer['anbieter']
        if anbieter not in offers_by_bank:
            offers_by_bank[anbieter] = []
        offers_by_bank[anbieter].append(offer)

    # Plot data for each bank (only Effektiver Zinssatz)
    for anbieter, offers in offers_by_bank.items():
        dates = [offer['angebotsdatum'] for offer in offers]
        eff_zins_values = [offer['effektivzinssatz'] for offer in offers]
        color = bank_colors.get(anbieter, '#333333')
        
        # Sort by date
        sorted_data = sorted(zip(dates, eff_zins_values), key=lambda x: x[0])
        sorted_dates, sorted_values = zip(*sorted_data) if sorted_data else ([], [])
        
        if sorted_dates:
            # Use scatter for marker-only visualization (no connecting lines)
            plt.scatter(
                sorted_dates,
                sorted_values,
                marker='d',
                s=100,  # Marker size
                color=color,
                label=anbieter,
                alpha=0.8,
                edgecolors=COLOR_PRIMARY,
                linewidths=1.5
            )
    
    # Customize plot with date range in title
    date_from = twelve_months_ago.strftime('%d.%m.%Y')
    date_to = datetime.now().strftime('%d.%m.%Y')
    plt.title(f'Wohnkredite - Konkurrenzangebote ({date_from} - {date_to})',
              fontsize=16, fontweight='bold', pad=15)
    plt.xlabel('Datum', fontsize=12, fontweight='bold')
    plt.ylabel('Sollzins (%)', fontsize=12, fontweight='bold')

    # Format x-axis
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%d.%m.%Y'))
    plt.xticks(rotation=45)

    # Add grid
    plt.grid(True, alpha=0.3, linestyle='--', linewidth=0.5)

    # Add legend (outside plot area)
    plt.legend(loc='center left', bbox_to_anchor=(1, 0.5),
               frameon=True, shadow=True, fontsize=8)

    # Set background
    plt.gca().set_facecolor('#fafafa')

    # Adjust layout
    plt.tight_layout()

    # Save to PNG file
    plt.savefig(INDIVIDUAL_OFFERS_CHART_PNG_PATH, dpi=150, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    
    # Save to bytes for base64 encoding
    from io import BytesIO
    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    buf.seek(0)
    png_bytes = buf.read()
    buf.close()
    
    # Close figure to free memory
    plt.close()
    
    # Convert to base64
    png_base64 = base64.b64encode(png_bytes).decode()
    
    return png_base64


def generate_static_png_chart(df, fixierung_values, laufzeit_values, colors):
    """Generate static PNG chart using matplotlib for email embedding - Default: 25J and Eff. Zinssatz only, last 12 months"""

    from datetime import timedelta

    # Filter to last 12 months
    twelve_months_ago = datetime.now() - timedelta(days=365)
    df_filtered = df[df['scrape_timestamp'] >= twelve_months_ago].copy()

    if df_filtered.empty:
        print("[WARN] No data in last 12 months, using all available data")
        df_filtered = df.copy()

    # Create figure
    plt.figure(figsize=(14, 7))

    # Default: Only show 25J Laufzeit and Effektiver Zinssatz
    target_laufzeit = 25
    show_zinssatz = False  # Only show Effektiver Zinssatz

    # Plot data for each Fixlaufzeit (only for 25J Laufzeit)
    for fixierung in fixierung_values:
        # Filter data for this combination (only 25J Laufzeit) from filtered dataframe
        mask = (df_filtered['fixierung_jahre'] == fixierung) & (df_filtered['run_laufzeit_jahre'] == target_laufzeit)
        data = df_filtered[mask].copy()
        
        if data.empty:
            continue
        
        data = data.sort_values('scrape_timestamp')
        color = colors.get(fixierung, '#333333')
        
        # Only plot Effektiver Zinssatz (dashed line)
        plt.plot(
            data['scrape_timestamp'],
            data['effektiver_zinssatz_numeric'],
            marker='s',
            linewidth=2.5,
            markersize=5,
            linestyle='--',
            color=color,
            label=f'{fixierung}J fix - 25J Eff. Zinssatz',
            alpha=0.8
        )
    
    # Customize plot with date range in title
    date_from = twelve_months_ago.strftime('%d.%m.%Y')
    date_to = datetime.now().strftime('%d.%m.%Y')
    plt.title(f'Wohnkredit Zinsentwicklung - 25J Laufzeit ({date_from} - {date_to})',
              fontsize=16, fontweight='bold', pad=15)
    plt.xlabel('Datum', fontsize=12, fontweight='bold')
    plt.ylabel('Effektiver Zinssatz (%)', fontsize=12, fontweight='bold')
    
    # Format x-axis
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%d.%m.%Y'))
    plt.xticks(rotation=45)
    
    # Add grid
    plt.grid(True, alpha=0.3, linestyle='--', linewidth=0.5)
    
    # Add legend (outside plot area)
    plt.legend(loc='center left', bbox_to_anchor=(1, 0.5), 
               frameon=True, shadow=True, fontsize=8)
    
    # Set background
    plt.gca().set_facecolor('#fafafa')
    
    # Adjust layout
    plt.tight_layout()
    
    # Save to PNG file
    plt.savefig(CHART_PNG_PATH, dpi=150, bbox_inches='tight', 
                facecolor='white', edgecolor='none')
    
    # Save to bytes for base64 encoding
    from io import BytesIO
    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    buf.seek(0)
    png_bytes = buf.read()
    buf.close()
    
    # Close figure to free memory
    plt.close()
    
    # Convert to base64
    png_base64 = base64.b64encode(png_bytes).decode()
    
    return png_base64


def get_all_runs_data():
    """Get all scraping runs with their variations"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get all runs
    cursor.execute("""
        SELECT * FROM scraping_runs 
        ORDER BY scrape_date DESC 
    """)
    
    runs = cursor.fetchall()
    column_names = [desc[0] for desc in cursor.description]
    runs_list = [dict(zip(column_names, run)) for run in runs]
    
    # Get variations for all runs
    all_variations = {}
    for run in runs_list:
        cursor.execute("""
            SELECT * FROM fixierung_variations 
            WHERE run_id = ?
            ORDER BY fixierung_jahre
        """, (run['id'],))
        
        variations = cursor.fetchall()
        variation_columns = [desc[0] for desc in cursor.description]
        all_variations[run['id']] = [dict(zip(variation_columns, v)) for v in variations]
    
    conn.close()
    
    return runs_list, all_variations


def get_latest_oenb_screenshots():
    """Get the latest OeNB chart screenshots"""
    screenshots = {}
    
    chart_patterns = {
        'demand_verah_durchschn_kreditsumme_chart': 'oenb_nachfrage_verah_durchschn_kreditsumme_*.png',
        'demand_nkv_zins_chart': 'oenb_nachfrage_nkv_zins_*.png'
    }
    
    if not SCREENSHOTS_DIR.exists():
        print("[WARN] Screenshots directory does not exist")
        return screenshots
    
    for chart_id, pattern in chart_patterns.items():
        matches = list(SCREENSHOTS_DIR.glob(pattern))
        if matches:
            # Sort by modification time, get the latest
            latest = max(matches, key=lambda p: p.stat().st_mtime)
            screenshots[chart_id] = latest
            print(f"[INFO] Found latest {chart_id}: {latest}")
        else:
            print(f"[WARN] No screenshot found for {chart_id} (pattern: {pattern})")
    
    return screenshots


def get_date_range_from_db():
    """
    Extract date range from housing loan database for SWAP/Euribor data fetching.
    
    Returns:
        Tuple of (start_date, end_date) as datetime objects.
        Defaults to last 12 months if no data available.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Check if view exists
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='view' AND name='housing_loan_chart_ready'
        """)
        view_exists = cursor.fetchone()
        
        if not view_exists:
            # Default to last 12 months, up to today (not truncated to month start)
            end_date = datetime.now()
            start_date = datetime(end_date.year - 1, end_date.month, 1)
            print(f"[INFO] View not found, using default date range: {start_date.strftime('%Y-%m')} to {end_date.strftime('%Y-%m-%d')}")
            return start_date, end_date
        
        # Get min and max scrape dates from the view
        cursor.execute("""
            SELECT 
                MIN(run_scrape_date) as min_date,
                MAX(run_scrape_date) as max_date
            FROM housing_loan_chart_ready
        """)
        
        result = cursor.fetchone()
        min_date_str = result[0]
        max_date_str = result[1]
        
        # SWAP/Euribor rates are independent of the housing-loan scraping runs,
        # so the upper bound should always be today (full precision), not the
        # last scrape date truncated to the 1st of the month - otherwise the
        # chart never shows data past the first few days of the current month.
        end_date = datetime.now()

        if min_date_str:
            try:
                min_date = datetime.fromisoformat(min_date_str.replace('Z', '+00:00'))

                # Ensure we have at least 12 months of data
                if (end_date - min_date).days < 365:
                    start_date = datetime(end_date.year - 1, end_date.month, 1)
                else:
                    start_date = min_date.replace(day=1)

                print(f"[INFO] Date range from DB: {start_date.strftime('%Y-%m')} to {end_date.strftime('%Y-%m-%d')}")
                return start_date, end_date
            except (ValueError, AttributeError) as e:
                print(f"[WARN] Could not parse dates from DB: {e}")

        # Fallback to default
        start_date = datetime(end_date.year - 1, end_date.month, 1)
        print(f"[INFO] Using default date range: {start_date.strftime('%Y-%m')} to {end_date.strftime('%Y-%m-%d')}")
        return start_date, end_date

    except Exception as e:
        print(f"[WARN] Error extracting date range from DB: {e}")
        # Fallback to default
        end_date = datetime.now()
        start_date = datetime(end_date.year - 1, end_date.month, 1)
        return start_date, end_date
    finally:
        conn.close()


def image_to_base64(image_path):
    """Convert image file to base64 string"""
    try:
        with open(image_path, 'rb') as img_file:
            import base64
            img_data = base64.b64encode(img_file.read()).decode('utf-8')
            # Detect image type from extension
            ext = image_path.suffix.lower()
            if ext == '.png':
                mime_type = 'image/png'
            elif ext in ['.jpg', '.jpeg']:
                mime_type = 'image/jpeg'
            else:
                mime_type = 'image/png'  # default
            return f"data:{mime_type};base64,{img_data}"
    except Exception as e:
        print(f"[WARN] Could not convert {image_path} to base64: {e}")
        return None


def generate_swap_rates_chart():
    """
    Generate interactive Plotly chart for SWAP rates (5Y, 10Y, 15Y, 20Y, 25Y maturities).
    
    Returns:
        Tuple of (chart_html, png_base64) or (None, None) if data unavailable
    """
    try:
        from swap_data_fetcher import fetch_all_rates
        
        # Get date range from database
        start_date, end_date = get_date_range_from_db()
        
        # Fetch SWAP/Euribor data
        print("[INFO] Fetching SWAP rates data...")
        rate_data = fetch_all_rates(start_date, end_date)
        
        if not rate_data:
            print("[WARN] No SWAP rate data available")
            return None, None
        
        # Extract SWAP rates by maturity
        swap_data_by_maturity = {
            '5Y': [],
            '10Y': [],
            '15Y': [],
            '20Y': [],
            '25Y': []
        }
        
        dates = []
        for day_data in rate_data:
            # Use the 'date' field (ISO format: YYYY-MM-DD)
            date_str = day_data.get('date')
            if date_str:
                dt = datetime.strptime(date_str, '%Y-%m-%d')
                dates.append(dt)

            rates = day_data.get('rates', {})
            for maturity in swap_data_by_maturity.keys():
                if maturity in rates:
                    swap_data_by_maturity[maturity].append(rates[maturity])
                else:
                    swap_data_by_maturity[maturity].append(None)
        
        # Create Plotly figure
        fig = go.Figure()
        
        # Colors for each maturity
        colors = {
            '5Y': '#1f77b4',   # Blue
            '10Y': '#2ca02c',   # Green
            '15Y': '#ff7f0e',   # Orange
            '20Y': '#d62728',   # Red
            '25Y': '#9467bd'    # Purple
        }
        
        # Add traces for each maturity. Only the first available maturity (5Y
        # by default) starts visible - the segmented pill selector in the HTML
        # shows exactly one maturity at a time via Plotly.restyle.
        maturities_present = []
        for maturity in ['5Y', '10Y', '15Y', '20Y', '25Y']:
            values = swap_data_by_maturity[maturity]
            if any(v is not None for v in values):
                fig.add_trace(go.Scatter(
                    x=dates,
                    y=values,
                    mode='lines+markers',
                    name=f'{maturity} SWAP',
                    line=dict(color=colors[maturity], width=2.5),
                    marker=dict(size=6, symbol='circle'),
                    hovertemplate=(
                        f'<b>{maturity} SWAP</b><br>'
                        'Datum: %{x|%d.%m.%Y}<br>'
                        'Zinssatz: %{y:.2f}%<br>'
                        '<extra></extra>'
                    ),
                    visible=(len(maturities_present) == 0)
                ))
                maturities_present.append(maturity)

        # Update layout (title lives in the surrounding HTML card header; no
        # legend needed since only one maturity is shown at a time)
        fig.update_layout(
            xaxis=dict(
                title=dict(text='Datum', font=dict(size=13, family=PLOTLY_FONT, color=COLOR_TEXT_MUTED)),
                tickfont=dict(color=COLOR_TEXT_MUTED, size=11),
                showgrid=True,
                gridwidth=1,
                gridcolor=COLOR_GRID,
                tickformat='%d.%m.%Y'
            ),
            yaxis=dict(
                title=dict(text='Zinssatz (%)', font=dict(size=13, family=PLOTLY_FONT, color=COLOR_TEXT_MUTED)),
                tickfont=dict(color=COLOR_TEXT_MUTED, size=11),
                showgrid=True,
                gridwidth=1,
                gridcolor=COLOR_GRID
            ),
            hovermode='closest',
            hoverlabel=dict(font=dict(family=PLOTLY_FONT, size=13, color=COLOR_TEXT), bgcolor='white', bordercolor=COLOR_GRID),
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            font=dict(family=PLOTLY_FONT, size=12, color=COLOR_TEXT),
            showlegend=False,
            height=420,
            margin=dict(l=60, r=30, t=20, b=50)
        )

        # Convert to HTML
        chart_html = fig.to_html(
            include_plotlyjs='cdn',
            div_id='plotly-swap-rates-chart',
            config={
                'displayModeBar': True,
                'displaylogo': False,
                'modeBarButtonsToRemove': ['select2d', 'lasso2d'],
                'responsive': True
            }
        )

        # Generate static PNG for email
        print("[INFO] Generating SWAP rates chart PNG for email...")
        try:
            png_base64 = generate_static_png_swap_rates(rate_data)
            print("[OK] SWAP rates chart PNG generated")
        except Exception as e:
            print(f"[WARN] Could not generate SWAP rates PNG: {e}")
            png_base64 = None

        # Generate table for last 5 months (10Y)
        try:
            table_html = generate_swap_10y_table_html(rate_data)
        except Exception as e:
            print(f"[WARN] Could not generate SWAP table: {e}")
            table_html = ''

        return chart_html, maturities_present, png_base64, table_html

    except ImportError as e:
        print(f"[WARN] swap_data_fetcher not available: {e}")
        return None, [], None, ''
    except Exception as e:
        print(f"[WARN] Error generating SWAP rates chart: {e}")
        return None, [], None, ''


def generate_euribor_chart():
    """
    Generate interactive Plotly chart for Euribor 3M.
    
    Returns:
        Tuple of (chart_html, png_base64) or (None, None) if data unavailable
    """
    try:
        from swap_data_fetcher import fetch_all_rates
        
        # Get date range from database
        start_date, end_date = get_date_range_from_db()
        
        # Fetch SWAP/Euribor data
        print("[INFO] Fetching Euribor data...")
        rate_data = fetch_all_rates(start_date, end_date)
        
        if not rate_data:
            print("[WARN] No Euribor data available")
            return None, None
        
        # Extract Euribor 3M data
        dates = []
        euribor_values = []

        for day_data in rate_data:
            # Use the 'date' field (ISO format: YYYY-MM-DD)
            date_str = day_data.get('date')
            if date_str:
                dt = datetime.strptime(date_str, '%Y-%m-%d')
                dates.append(dt)

            rates = day_data.get('rates', {})
            if '3M' in rates:
                euribor_values.append(rates['3M'])
            else:
                euribor_values.append(None)
        
        if not any(v is not None for v in euribor_values):
            print("[WARN] No Euribor 3M data in fetched rates")
            return None, None
        
        # Create Plotly figure
        fig = go.Figure()
        
        fig.add_trace(go.Scatter(
            x=dates,
            y=euribor_values,
            mode='lines+markers',
            name='Euribor 3M',
            line=dict(color=COLOR_ACCENT, width=2.5),
            marker=dict(size=6, symbol='circle'),
            hovertemplate=(
                '<b>Euribor 3M</b><br>'
                'Datum: %{x|%d.%m.%Y}<br>'
                'Zinssatz: %{y:.2f}%<br>'
                '<extra></extra>'
            )
        ))

        # Update layout (title lives in the surrounding HTML card header)
        fig.update_layout(
            xaxis=dict(
                title=dict(text='Datum', font=dict(size=13, family=PLOTLY_FONT, color=COLOR_TEXT_MUTED)),
                tickfont=dict(color=COLOR_TEXT_MUTED, size=11),
                showgrid=True,
                gridwidth=1,
                gridcolor=COLOR_GRID,
                tickformat='%d.%m.%Y'
            ),
            yaxis=dict(
                title=dict(text='Zinssatz (%)', font=dict(size=13, family=PLOTLY_FONT, color=COLOR_TEXT_MUTED)),
                tickfont=dict(color=COLOR_TEXT_MUTED, size=11),
                showgrid=True,
                gridwidth=1,
                gridcolor=COLOR_GRID
            ),
            hovermode='closest',
            hoverlabel=dict(font=dict(family=PLOTLY_FONT, size=13, color=COLOR_TEXT), bgcolor='white', bordercolor=COLOR_GRID),
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            font=dict(family=PLOTLY_FONT, size=12, color=COLOR_TEXT),
            showlegend=False,
            height=380,
            margin=dict(l=60, r=30, t=20, b=50)
        )
        
        # Convert to HTML
        chart_html = fig.to_html(
            include_plotlyjs='cdn',
            div_id='plotly-euribor-chart',
            config={
                'displayModeBar': True,
                'displaylogo': False,
                'modeBarButtonsToRemove': ['select2d', 'lasso2d'],
                'responsive': True
            }
        )
        
        # Generate static PNG for email
        print("[INFO] Generating Euribor chart PNG for email...")
        try:
            png_base64 = generate_static_png_euribor(rate_data)
            print("[OK] Euribor chart PNG generated")
        except Exception as e:
            print(f"[WARN] Could not generate Euribor PNG: {e}")
            png_base64 = None
        
        return chart_html, png_base64
        
    except ImportError as e:
        print(f"[WARN] swap_data_fetcher not available: {e}")
        return None, None
    except Exception as e:
        print(f"[WARN] Error generating Euribor chart: {e}")
        return None, None


def generate_static_png_swap_rates(rate_data):
    """Generate static PNG chart for SWAP rates using matplotlib (10Y only for email)"""
    dates = []
    swap_10y = []

    for day_data in rate_data:
        # Use the 'date' field (ISO format: YYYY-MM-DD)
        date_str = day_data.get('date')
        if date_str:
            dt = datetime.strptime(date_str, '%Y-%m-%d')
            dates.append(dt)

        rates = day_data.get('rates', {})
        if '10Y' in rates:
            swap_10y.append(rates['10Y'])
        else:
            swap_10y.append(None)

    fig, ax = plt.subplots(figsize=(14, 8))

    # Only plot 10Y line
    if any(v is not None for v in swap_10y):
        ax.plot(dates, swap_10y, label='10Y SWAP', color='#2ca02c',
               linewidth=2.5, marker='o', markersize=4)

    ax.set_xlabel('Datum', fontsize=12, fontfamily='Arial')
    ax.set_ylabel('Zinssatz (%)', fontsize=12, fontfamily='Arial')
    ax.set_title('EUR SWAP Rates (10 Jahre)', fontsize=16, fontweight='bold', fontfamily='Arial', pad=20)
    ax.grid(True, alpha=0.3, linestyle='--')
    ax.legend(loc='best', fontsize=10)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d.%m.%Y'))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=max(1, len(dates)//12)))
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    
    # Convert to base64
    from io import BytesIO
    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    img_base64 = base64.b64encode(buf.read()).decode('utf-8')
    plt.close(fig)
    
    return f"data:image/png;base64,{img_base64}"


def generate_swap_10y_table_html(rate_data):
    """
    Generate HTML table for last 5 months of 10Y SWAP rates.

    Args:
        rate_data: List of daily rate data from swap_data_fetcher

    Returns:
        HTML string for the table
    """
    if not rate_data:
        return '<p style="text-align: center; color: #666; padding: 20px;">Keine Daten verfügbar</p>'

    # Group by month and calculate average for each month
    from collections import defaultdict
    monthly_data = defaultdict(list)

    for day_data in rate_data:
        date_str = day_data.get('date')
        if not date_str:
            continue

        try:
            dt = datetime.strptime(date_str, '%Y-%m')
            month_key = dt.strftime('%Y-%m')
        except:
            try:
                dt = datetime.strptime(date_str, '%Y-%m-%d')
                month_key = dt.strftime('%Y-%m')
            except:
                continue

        rates = day_data.get('rates', {})
        if '10Y' in rates and rates['10Y'] is not None:
            monthly_data[month_key].append(rates['10Y'])

    # Calculate monthly averages
    monthly_avg = []
    for month in sorted(monthly_data.keys()):
        values = monthly_data[month]
        if values:
            avg = sum(values) / len(values)
            monthly_avg.append({
                'month': month,
                'avg': avg
            })

    # Get last 5 months
    last_5 = monthly_avg[-5:] if len(monthly_avg) >= 5 else monthly_avg

    if not last_5:
        return '<p style="text-align: center; color: #666; padding: 20px;">Keine Daten verfügbar</p>'

    # Format month names
    def format_month(month_str):
        try:
            dt = datetime.strptime(month_str, '%Y-%m')
            month_names = ['Jän', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun',
                          'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']
            return f"{month_names[dt.month-1]} {dt.year}"
        except:
            return month_str

    rows_html = '\n'.join([
        f'''                        <tr>
                            <td style="padding: 12px; text-align: left; border-bottom: 1px solid #eee;">{format_month(item['month'])}</td>
                            <td style="padding: 12px; text-align: left; border-bottom: 1px solid #eee;">{item['avg']:.3f}%</td>
                        </tr>'''
        for item in last_5
    ])

    return f'''
            <div class="table-container" style="margin-top: 24px;">
                <h3 style="margin-bottom: 16px; font-size: 16px; color: #1b2733;">📊 Entwicklung letzte 5 Monate - EUR SWAP Rates (10 Jahre)</h3>
                <table style="width: 100%; border-collapse: collapse;">
                    <thead>
                        <tr style="background-color: #f5f5f5;">
                            <th style="padding: 12px; text-align: left; border-bottom: 2px solid #ddd;">Monat</th>
                            <th style="padding: 12px; text-align: left; border-bottom: 2px solid #ddd;">Durchschnitt</th>
                        </tr>
                    </thead>
                    <tbody>
{rows_html}
                    </tbody>
                </table>
            </div>'''


def generate_static_png_euribor(rate_data):
    """Generate static PNG chart for Euribor 3M using matplotlib"""
    dates = []
    euribor_values = []

    for day_data in rate_data:
        # Use the 'date' field (ISO format: YYYY-MM-DD)
        date_str = day_data.get('date')
        if date_str:
            dt = datetime.strptime(date_str, '%Y-%m-%d')
            dates.append(dt)

        rates = day_data.get('rates', {})
        if '3M' in rates:
            euribor_values.append(rates['3M'])
        else:
            euribor_values.append(None)
    
    fig, ax = plt.subplots(figsize=(14, 8))
    
    ax.plot(dates, euribor_values, label='Euribor 3M', color='#1f77b4', 
           linewidth=2.5, marker='o', markersize=4)
    
    ax.set_xlabel('Datum', fontsize=12, fontfamily='Arial')
    ax.set_ylabel('Zinssatz (%)', fontsize=12, fontfamily='Arial')
    ax.set_title('Euribor 3M', fontsize=16, fontweight='bold', fontfamily='Arial', pad=20)
    ax.grid(True, alpha=0.3, linestyle='--')
    ax.legend(loc='best', fontsize=10)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d.%m.%Y'))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=max(1, len(dates)//12)))
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    
    # Convert to base64
    from io import BytesIO
    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    img_base64 = base64.b64encode(buf.read()).decode('utf-8')
    plt.close(fig)
    
    return f"data:image/png;base64,{img_base64}"


def generate_swap_euribor_section_html(swap_chart_html, euribor_chart_html, swap_png_base64, euribor_png_base64,
                                        for_email=False, swap_maturities=None, swap_table_html=''):
    """Generate HTML section for SWAP/Euribor charts

    Args:
        swap_chart_html: Plotly HTML for SWAP rates chart (None if unavailable)
        euribor_chart_html: Plotly HTML for Euribor chart (None if unavailable)
        swap_png_base64: Base64 PNG for SWAP rates (for email)
        euribor_png_base64: Base64 PNG for Euribor (for email)
        for_email: if True, use base64 PNG; if False, use Plotly HTML
        swap_maturities: list of maturity labels (e.g. ['5Y', '10Y', ...]) present
            as traces in swap_chart_html, in trace order - used to build the
            segmented pill selector that shows one maturity at a time
        swap_table_html: HTML table for last 5 months of 10Y SWAP rates
    """
    if not swap_chart_html and not euribor_chart_html:
        return ""

    swap_maturities = swap_maturities or []

    section_html = '''
        <div class="swap-euribor-section" style="margin-top: 40px;">
            <h2 style="text-align: center; margin-bottom: 20px;">📈 Marktzinsen (SWAP &amp; Euribor)</h2>
'''

    if for_email:
        # Use static PNG images for email
        if swap_png_base64:
            section_html += f'''
            <div class="chart-container">
                <div class="chart-title">EUR SWAP Rates</div>
                <img src="{swap_png_base64}" alt="EUR SWAP Rates" style="width: 100%; max-width: 1400px; height: auto; border-radius: 8px;" />
                {swap_table_html}
            </div>
'''
        if euribor_png_base64:
            section_html += f'''
            <div class="chart-container">
                <div class="chart-title">Euribor 3M</div>
                <img src="{euribor_png_base64}" alt="Euribor 3M" style="width: 100%; max-width: 1400px; height: auto; border-radius: 8px;" />
            </div>
'''
    else:
        # Use interactive Plotly charts for web
        if swap_chart_html:
            pills = ''.join(
                f'<button class="swap-maturity-btn{" active" if i == 0 else ""}" '
                f'onclick="setSwapMaturity(\'{m}\')" data-maturity="{m}">{m}</button>'
                for i, m in enumerate(swap_maturities)
            )
            section_html += f'''
            <div class="chart-container">
                <div class="chart-title">EUR SWAP Rates</div>
                <div class="segmented-control" id="swap-maturity-selector">{pills}</div>
                {swap_chart_html}
                <script>
                    const swapMaturities = {json.dumps(swap_maturities)};
                    function setSwapMaturity(maturity) {{
                        const idx = swapMaturities.indexOf(maturity);
                        if (idx === -1) return;
                        const visible = swapMaturities.map((m, i) => i === idx);
                        Plotly.restyle('plotly-swap-rates-chart', {{'visible': visible}});
                        document.querySelectorAll('.swap-maturity-btn').forEach(btn => {{
                            btn.classList.toggle('active', btn.dataset.maturity === maturity);
                        }});
                    }}
                </script>
                {swap_table_html}
            </div>
'''
        if euribor_chart_html:
            section_html += f'''
            <div class="chart-container">
                <div class="chart-title">Euribor 3M</div>
                {euribor_chart_html}
            </div>
'''

    section_html += '''
        </div>
'''
    return section_html


def generate_oenb_data_table_html(chart_id: str) -> str:
    """
    Render a compact table with the last 5 periods of a chart's underlying
    numeric series (extracted best-effort by oenb_nachfrage_scraper.py).
    Returns '' if no data is available yet - the screenshot above still
    renders on its own in that case.
    """
    try:
        table_data = get_latest_oenb_table_data(chart_id, limit=5)
    except Exception as e:
        print(f"[WARN] Could not load OeNB table data for '{chart_id}': {e}")
        return ""

    if not table_data:
        return ""

    series_names = table_data['series_names']
    rows = table_data['rows']

    header_cells = ''.join(f'<th>{name}</th>' for name in series_names)
    body_rows = ''
    for row in rows:
        value_cells = ''
        for name in series_names:
            value = row['values'].get(name)
            value_cells += f'<td>{value:,.2f}</td>' if isinstance(value, (int, float)) else '<td>-</td>'
        body_rows += f"<tr><td class=\"fixierung-cell\">{row['period']}</td>{value_cells}</tr>"

    return f'''
                <div class="table-container" style="margin-top: 16px;">
                    <table>
                        <thead><tr><th>Zeitraum</th>{header_cells}</tr></thead>
                        <tbody>{body_rows}</tbody>
                    </table>
                </div>'''


def generate_oenb_section_html(screenshots, for_email=False):
    """Generate HTML section for OeNB charts

    Args:
        screenshots: dict mapping chart_id to screenshot path
        for_email: if True, use base64 encoding; if False, use relative paths
    """
    if not screenshots:
        return ""

    oenb_html = '''
        <div class="oenb-section" style="margin-top: 40px;">
            <h2 style="text-align: center; margin-bottom: 20px;">📊 OeNB Wohnimmobilien Dashboard</h2>
'''

    chart_names = {
        'demand_verah_durchschn_kreditsumme_chart': 'Durchschnittliche Kreditsumme (Veränderung)',
        'demand_nkv_zins_chart': 'Nettokreditvolumen & Zinssatz'
    }

    for chart_id, screenshot_path in screenshots.items():
        chart_name = chart_names.get(chart_id, chart_id)

        if for_email:
            # Use base64 encoding for email
            img_src = image_to_base64(screenshot_path)
            if not img_src:
                continue  # Skip if conversion failed
        else:
            # Use relative path for web version
            img_src = f"screenshots/{screenshot_path.name}"

        data_table_html = generate_oenb_data_table_html(chart_id)

        oenb_html += f'''
            <div class="chart-container">
                <div class="chart-title">{chart_name}</div>
                <img src="{img_src}" alt="{chart_name}" style="width: 100%; max-width: 1400px; height: auto; border-radius: 8px;" />{data_table_html}
            </div>
'''

    oenb_html += '''
        </div>
'''
    return oenb_html


def generate_html():
    """Generate HTML page with interactive Plotly chart and data tables"""
    
    # Generate Durchblicker chart
    chart_html, laufzeit_values, fixierung_values, trace_metadata, png_base64 = generate_interactive_chart()
    
    if not chart_html:
        print("[WARN] No data found in database")
        return False, None
    
    # Generate competitor trend charts (NEW: replaces individual offers chart)
    print("[INFO] Generating competitor trend charts...")
    try:
        sollzins_chart_html, sollzins_fixierung_values, sollzins_data, sollzins_table_html = generate_competitor_sollzins_chart(
            DB_PATH, PLOTLY_FONT, COLOR_PRIMARY, COLOR_ACCENT, COLOR_TEXT, COLOR_GRID
        )
        effektivzins_chart_html, effektivzins_fixierung_values, effektivzins_data, effektivzins_table_html = generate_competitor_effektivzins_chart(
            DB_PATH, PLOTLY_FONT, COLOR_PRIMARY, COLOR_ACCENT, COLOR_TEXT, COLOR_GRID
        )

        # Generate PNG versions for email
        sollzins_png_base64 = generate_static_png_competitor_sollzins(sollzins_data) if sollzins_data else None
        effektivzins_png_base64 = generate_static_png_competitor_effektivzins(effektivzins_data) if effektivzins_data else None

        print(f"[INFO] Sollzins chart: {sollzins_chart_html is not None}, PNG: {sollzins_png_base64 is not None}")
        print(f"[INFO] Effektivzins chart: {effektivzins_chart_html is not None}, PNG: {effektivzins_png_base64 is not None}")
    except Exception as e:
        print(f"[ERROR] Failed to generate competitor trend charts: {e}")
        import traceback
        traceback.print_exc()
        sollzins_chart_html = None
        sollzins_fixierung_values = []
        sollzins_png_base64 = None
        sollzins_table_html = ''
        effektivzins_chart_html = None
        effektivzins_fixierung_values = []
        effektivzins_png_base64 = None
        effektivzins_table_html = ''

    # Lowest Sollzins per bank in the last 30 days, for the table under the
    # competitor charts
    try:
        lowest_offers_table_html = generate_lowest_offers_table_html(get_all_loan_offers(), days=30)
    except Exception as e:
        print(f"[WARN] Could not build lowest-offers table: {e}")
        lowest_offers_table_html = ''

    # Get all runs data
    runs, all_variations = get_all_runs_data()
    
    # Get latest OeNB screenshots
    oenb_screenshots = get_latest_oenb_screenshots()
    
    # Generate SWAP/Euribor charts
    print("[INFO] Generating SWAP/Euribor charts...")
    swap_chart_result = generate_swap_rates_chart()
    euribor_chart_result = generate_euribor_chart()

    if swap_chart_result[0]:
        swap_chart_html, swap_maturities, swap_png_base64, swap_table_html = swap_chart_result
    else:
        swap_chart_html, swap_maturities, swap_png_base64, swap_table_html = None, [], None, ''

    if euribor_chart_result[0]:
        euribor_chart_html, euribor_png_base64 = euribor_chart_result
    else:
        euribor_chart_html, euribor_png_base64 = None, None

    if not runs:
        print("[WARN] No data found in database")
        return False, None
    
    # Get latest run (used for the footer timestamp's Run ID)
    latest_run = runs[0]

    # Organize runs by Laufzeit for dynamic table updates
    runs_by_laufzeit = {}
    for run in runs:
        laufzeit = run['laufzeit_jahre']
        if laufzeit not in runs_by_laufzeit:
            runs_by_laufzeit[laufzeit] = []
        runs_by_laufzeit[laufzeit].append({
            'run': run,
            'variations': all_variations[run['id']]
        })
    
    # Get the latest and previous run for each Laufzeit
    latest_by_laufzeit = {}
    previous_by_laufzeit = {}
    for laufzeit, runs_list in runs_by_laufzeit.items():
        # Sort by date descending and get the latest + previous run (at least
        # 6 days earlier, so re-running the pipeline mid-week during testing
        # doesn't turn the trend into a same-day/same-week comparison)
        sorted_runs = sorted(runs_list, key=lambda x: x['run']['scrape_date'], reverse=True)
        latest_by_laufzeit[laufzeit] = sorted_runs[0]
        previous_by_laufzeit[laufzeit] = find_previous_run(sorted_runs, min_gap_days=6)

    # Prepare table data for JavaScript (must be JSON-serializable)
    table_data_for_js = {}
    for laufzeit, data in latest_by_laufzeit.items():
        previous = previous_by_laufzeit.get(laufzeit)
        table_data_for_js[int(laufzeit)] = {
            'run': data['run'],
            'variations': data['variations'],
            'previous_variations': previous['variations'] if previous else None
        }

    # Initial trend table state, matching the Laufzeit dropdown's default (25J)
    default_trend_laufzeit = 25 if 25 in table_data_for_js else (
        sorted(table_data_for_js.keys())[0] if table_data_for_js else None
    )
    initial_trend_rows = []
    if default_trend_laufzeit is not None:
        default_trend_data = table_data_for_js[default_trend_laufzeit]
        initial_trend_rows = compute_trend_rows(
            default_trend_data['variations'], default_trend_data['previous_variations']
        )
    initial_trend_tbody_html = ''.join(
        f'''
                        <tr>
                            <td class="fixierung-cell">{row['fixierung_jahre']}J</td>
                            <td>{row['previous_short']}</td>
                            <td>{row['current_short']}</td>
                            <td>{trend_badge_html(row['trend'])}</td>
                        </tr>'''
        for row in initial_trend_rows
    )
    
    # Create HTML content
    html_content = f'''<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bank Comparison - Housing Loan Analysis (Interactive)</title>
    <style>
        :root {{
            --color-bg: #f2f5f7;
            --color-surface: #ffffff;
            --color-primary: #0f3b52;
            --color-primary-dark: #0a2b3d;
            --color-accent: #0a8a9a;
            --color-accent-light: #e3f4f6;
            --color-text: #1b2733;
            --color-text-muted: #5b6b78;
            --color-border: #e2e8ee;
            --radius-sm: 8px;
            --radius-md: 12px;
            --radius-lg: 16px;
            --shadow-sm: 0 1px 3px rgba(15, 59, 82, 0.08);
            --shadow-md: 0 6px 20px rgba(15, 59, 82, 0.09);
            --font-sans: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
        }}
        * {{
            box-sizing: border-box;
        }}
        body {{
            font-family: var(--font-sans);
            margin: 0;
            padding: clamp(10px, 3vw, 24px);
            background: var(--color-bg);
            color: var(--color-text);
            min-height: 100vh;
            -webkit-font-smoothing: antialiased;
        }}
        .container {{
            max-width: 1440px;
            margin: 0 auto;
            background-color: var(--color-surface);
            padding: clamp(16px, 3vw, 36px);
            border-radius: var(--radius-lg);
            box-shadow: var(--shadow-md);
        }}
        h1 {{
            color: var(--color-primary);
            text-align: center;
            margin: 4px 0 6px;
            font-size: clamp(1.3em, 4vw, 2.1em);
            font-weight: 700;
            letter-spacing: -0.01em;
        }}
        h2 {{
            color: var(--color-primary);
            font-weight: 700;
            font-size: clamp(1.1em, 3vw, 1.6em);
        }}
        .subtitle {{
            text-align: center;
            color: var(--color-text-muted);
            margin-bottom: clamp(16px, 3vw, 28px);
            font-size: clamp(0.85em, 2vw, 1.05em);
        }}
        .info-badge {{
            background: var(--color-accent-light);
            color: var(--color-primary);
            padding: 8px 16px;
            border-radius: 20px;
            display: inline-block;
            margin: 4px;
            font-size: 0.85em;
            font-weight: 600;
        }}
        .chart-container {{
            margin-bottom: clamp(24px, 4vw, 40px);
            padding: clamp(12px, 3vw, 24px);
            background: var(--color-surface);
            border: 1px solid var(--color-border);
            border-radius: var(--radius-lg);
            box-shadow: var(--shadow-sm);
        }}
        .chart-title {{
            font-size: clamp(1.05em, 2.4vw, 1.4em);
            font-weight: 700;
            color: var(--color-primary);
            margin: 0 0 16px;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        /* Accordions used for filter toolbars and the competitor-offer form */
        details.filters-accordion, details.accordion {{
            background: var(--color-accent-light);
            border-radius: var(--radius-md);
            margin-bottom: 18px;
            border: 1px solid var(--color-border);
            overflow: hidden;
        }}
        details.accordion {{
            background: var(--color-surface);
        }}
        details.filters-accordion > summary, details.accordion > summary {{
            list-style: none;
            cursor: pointer;
            padding: 12px 18px;
            font-weight: 700;
            color: var(--color-primary);
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 10px;
            font-size: 0.95em;
        }}
        details.filters-accordion > summary::-webkit-details-marker,
        details.accordion > summary::-webkit-details-marker {{
            display: none;
        }}
        details.filters-accordion > summary::after,
        details.accordion > summary::after {{
            content: '▾';
            transition: transform 0.2s;
            color: var(--color-accent);
            font-size: 1.1em;
        }}
        details[open].filters-accordion > summary::after,
        details[open].accordion > summary::after {{
            transform: rotate(180deg);
        }}
        .filters-summary-chip {{
            font-weight: 500;
            color: var(--color-text-muted);
            font-size: 0.85em;
        }}
        .accordion-body {{
            padding: 0 18px 18px;
        }}
        .chart-controls {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
            gap: 14px 20px;
            align-items: end;
            padding: 16px 18px;
        }}
        .control-group {{
            display: flex;
            flex-direction: column;
            gap: 6px;
        }}
        .control-group.segmented {{
            grid-column: 1 / -1;
        }}
        .control-label {{
            font-weight: 600;
            color: var(--color-primary);
            font-size: 13px;
            white-space: nowrap;
        }}
        select {{
            padding: 9px 12px;
            border: 1px solid var(--color-border);
            border-radius: var(--radius-sm);
            font-size: 14px;
            font-family: var(--font-sans);
            cursor: pointer;
            background: var(--color-surface);
            color: var(--color-text);
            min-height: 40px;
            transition: border-color 0.2s;
        }}
        select:hover, select:focus {{
            border-color: var(--color-accent);
            outline: none;
        }}
        /* Segmented pill control (Anzeigen buttons, SWAP maturity selector) */
        .segmented-control {{
            display: inline-flex;
            flex-wrap: wrap;
            gap: 6px;
            background: var(--color-surface);
            border: 1px solid var(--color-border);
            border-radius: 999px;
            padding: 4px;
        }}
        .segmented-control button {{
            border: none;
            background: transparent;
            color: var(--color-text-muted);
            padding: 8px 16px;
            border-radius: 999px;
            font-size: 13px;
            font-weight: 600;
            font-family: var(--font-sans);
            cursor: pointer;
            transition: all 0.2s;
            min-height: 34px;
            white-space: nowrap;
        }}
        .segmented-control button:hover {{
            color: var(--color-primary);
        }}
        .segmented-control button.active {{
            background: var(--color-primary);
            color: white;
        }}
        .table-container {{
            overflow-x: auto;
            margin-bottom: 24px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 16px;
            font-size: 0.9em;
        }}
        th {{
            background: var(--color-primary);
            color: white;
            padding: 12px 12px;
            text-align: left;
            font-weight: 600;
            position: sticky;
            top: 0;
        }}
        td {{
            padding: 11px 12px;
            border-bottom: 1px solid var(--color-border);
        }}
        tr:hover {{
            background-color: var(--color-accent-light);
        }}
        tr:nth-child(even) {{
            background-color: #f8fafb;
        }}
        .fixierung-cell {{
            font-weight: 700;
            color: var(--color-primary);
            background-color: var(--color-accent-light) !important;
            border-left: 4px solid var(--color-accent);
        }}
        .rate-cell {{
            font-weight: 700;
            color: var(--color-primary);
            font-size: 1.05em;
        }}
        .timestamp {{
            text-align: center;
            color: var(--color-text-muted);
            font-size: 0.85em;
            margin-top: 28px;
            padding-top: 18px;
            border-top: 1px solid var(--color-border);
        }}
        .highlight {{
            background-color: #fff3cd !important;
        }}
        @media (max-width: 768px) {{
            body {{
                padding: 8px;
            }}
            .container {{
                padding: 12px;
                border-radius: var(--radius-md);
            }}
            .info-badge {{
                font-size: 0.8em;
                padding: 6px 12px;
                margin: 3px;
            }}
            .chart-container {{
                padding: 12px;
                margin-bottom: 18px;
            }}
            .chart-controls {{
                grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
                gap: 10px 12px;
                padding: 12px;
            }}
            .segmented-control button {{
                padding: 7px 12px;
                font-size: 12px;
                min-height: 32px;
            }}
            /* Plotly chart mobile adjustments */
            #plotly-chart, #plotly-individual-offers-chart {{
                height: 400px !important;
            }}
            .js-plotly-plot .plotly .modebar {{
                display: none !important;
            }}
            .js-plotly-plot .plotly .legend {{
                display: none !important;
            }}
            table {{
                font-size: 13px;
                min-width: 560px;
            }}
            th, td {{
                padding: 9px 8px;
                white-space: nowrap;
            }}
            .table-container {{
                margin-bottom: 18px;
            }}
            .timestamp {{
                font-size: 0.8em;
                margin-top: 18px;
                padding-top: 14px;
            }}
        }}
        @media (max-width: 480px) {{
            body {{
                padding: 6px;
            }}
            .container {{
                padding: 8px;
            }}
            .chart-container {{
                padding: 8px;
            }}
            .chart-controls {{
                grid-template-columns: 1fr 1fr;
                padding: 10px;
            }}
            .control-group.segmented {{
                grid-column: 1 / -1;
            }}
            .segmented-control {{
                width: 100%;
                justify-content: stretch;
            }}
            .segmented-control button {{
                flex: 1;
            }}
            #plotly-chart, #plotly-individual-offers-chart {{
                height: 300px !important;
            }}
            table {{
                font-size: 12px;
                min-width: 520px;
            }}
            th, td {{
                padding: 8px 6px;
            }}
        }}
        .nav-tabs {{
            display: flex;
            gap: 6px;
            margin-bottom: 24px;
            background-color: var(--color-bg);
            border-radius: 999px;
            padding: 5px;
        }}
        .nav-tab {{
            flex: 1;
            padding: 12px 18px;
            text-align: center;
            background-color: transparent;
            color: var(--color-text-muted);
            text-decoration: none;
            font-weight: 700;
            font-size: 0.95em;
            transition: all 0.2s ease;
            border: none;
            cursor: pointer;
            border-radius: 999px;
        }}
        .nav-tab:hover {{
            color: var(--color-primary);
            text-decoration: none;
        }}
        .nav-tab.active {{
            background-color: var(--color-primary);
            color: white;
            box-shadow: var(--shadow-sm);
        }}
        @media (max-width: 768px) {{
            .nav-tabs {{
                margin-bottom: 18px;
            }}
            .nav-tab {{
                padding: 10px 10px;
                font-size: 0.85em;
            }}
        }}
        @media (max-width: 480px) {{
            .nav-tab {{
                padding: 9px 6px;
                font-size: 0.78em;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="nav-tabs">
            <a href="#" class="nav-tab active">🏠 Housing Loans</a>
            <a href="bank_comparison_consumer_loan.html" class="nav-tab">🏦 Consumer Loans</a>
        </div>
        <h1>🏠 Housing Loan Comparison</h1>

        <script>
            // Filter accordions start expanded on desktop, collapsed on mobile.
            // Runs on DOMContentLoaded since this script tag is parsed before
            // the accordions further down the page exist yet.
            document.addEventListener('DOMContentLoaded', function() {{
                document.querySelectorAll('details.filters-accordion').forEach(function(d) {{
                    d.open = window.innerWidth > 768;
                }});
            }});
        </script>

        <div class="chart-container">
            <div class="chart-title">📈 Wohnkredite - Durchblicker-Bestpreis</div>
            <details class="filters-accordion">
                <summary>🔧 Filter &amp; Anzeige</summary>
                <div class="accordion-body">
                <div class="chart-controls">
                <div class="control-group">
                    <span class="control-label">Laufzeit:</span>
                    <select id="laufzeit-filter">
                        <option value="all">Alle Laufzeiten</option>
{f''.join([f'                        <option value="{lz}"{" selected" if lz == 25 else ""}>{lz} Jahre</option>\n' for lz in laufzeit_values])}                    </select>
                </div>
                <div class="control-group">
                    <span class="control-label">Fixlaufzeit:</span>
                    <select id="fixierung-filter">
                        <option value="all">Alle Fixlaufzeiten</option>
{f''.join([f'                        <option value="{fx}">{fx} Jahre</option>\n' for fx in fixierung_values])}                    </select>
                </div>
                <div class="control-group segmented">
                    <span class="control-label">Anzeigen:</span>
                    <div class="segmented-control">
                        <button id="btn-beide" onclick="setZinssatzFilter('beide')">Beide</button>
                        <button id="btn-zinssatz" class="active" onclick="setZinssatzFilter('zinssatz')">Nur Sollzins</button>
                        <button id="btn-effektiver" onclick="setZinssatzFilter('effektiver')">Nur Eff. Zinssatz</button>
                    </div>
                </div>
                </div>
                </div>
            </details>

            {chart_html}

            <div class="table-container" style="margin-top: 24px;">
                <h2 id="trend-table-title" style="margin-bottom: 16px;">📊 Trend - Sollzins je Fixlaufzeit ({default_trend_laufzeit or '–'} Jahre Laufzeit)</h2>
                <table>
                    <thead>
                        <tr>
                            <th>FixLZ</th>
                            <th>Voriger Lauf</th>
                            <th>Aktueller Lauf</th>
                            <th>Trend</th>
                        </tr>
                    </thead>
                    <tbody id="trend-tbody">{initial_trend_tbody_html}
                    </tbody>
                </table>
            </div>

            <script>
                // Store trace metadata
                const traceMetadata = {json.dumps(trace_metadata)};

                // Store table data for each Laufzeit
                const tableData = {json.dumps(table_data_for_js)};
                
                // Current filter states
                let currentLaufzeit = '25';
                let currentFixierung = 'all';
                let currentZinssatz = 'zinssatz';
                
                // Apply combined filters (chart + tables)
                function applyFilters() {{
                    const data = document.getElementById('plotly-chart').data;
                    
                    // Update chart visibility
                    const visible = [];
                    
                    for (let i = 0; i < traceMetadata.length && i < data.length; i++) {{
                        const meta = traceMetadata[i];
                        
                        // Handle scraped data filtering (Durchblicker data only)
                            // Check Laufzeit filter
                            const laufzeitMatch = currentLaufzeit === 'all' || meta.laufzeit === parseInt(currentLaufzeit);
                            
                            // Check Fixierung filter
                            const fixierungMatch = currentFixierung === 'all' || (meta.fixierung !== null && meta.fixierung === parseInt(currentFixierung));
                            
                            // Check Zinssatz type filter
                            let zinssatzMatch = true;
                            if (currentZinssatz === 'zinssatz') {{
                                zinssatzMatch = meta.type === 'zinssatz';
                            }} else if (currentZinssatz === 'effektiver') {{
                                zinssatzMatch = meta.type === 'effektiver';
                            }}
                            // 'beide' means both are shown, so zinssatzMatch stays true
                            
                            // Return true only if ALL conditions match (AND logic)
                            visible.push(laufzeitMatch && fixierungMatch && zinssatzMatch);
                    }}
                    
                    // Update the Plotly chart
                    Plotly.restyle('plotly-chart', {{'visible': visible}});
                    
                    // Update tables based on Laufzeit
                    updateTables();
                }}
                
                // Update tables based on current Laufzeit filter
                function updateTables() {{
                    if (currentLaufzeit === 'all') {{
                        // Show latest overall run (could be any Laufzeit)
                        const latestLaufzeit = 25;
                        renderTables(tableData[latestLaufzeit], latestLaufzeit);
                    }} else {{
                        // Show latest run for selected Laufzeit
                        const laufzeit = parseInt(currentLaufzeit);
                        if (tableData[laufzeit]) {{
                            renderTables(tableData[laufzeit], laufzeit);
                        }}
                    }}
                }}

                // Parse a German-formatted rate string like '3,490 % p.a.' into 3.49
                function parseSollzins(str) {{
                    if (!str) return null;
                    const m = str.match(/\\s*(-?[\\d.,]+)/);
                    if (!m) return null;
                    const num = parseFloat(m[1].replace(/\\./g, '').replace(',', '.'));
                    return isNaN(num) ? null : num;
                }}

                // Compact '3,320%' display - no ' p.a.' suffix or fixierung annotations
                function formatSollzins(value) {{
                    if (value === null || value === undefined) return '–';
                    return value.toFixed(3).replace('.', ',') + '%';
                }}

                function trendBadge(trend) {{
                    if (trend === 'up') return '<span style="color:#c0392b; font-weight:700;">▲ Anstieg</span>';
                    if (trend === 'down') return '<span style="color:#1e8449; font-weight:700;">▼ Rückgang</span>';
                    if (trend === 'flat') return '<span style="color:#7f8c8d; font-weight:700;">▬ Unverändert</span>';
                    return '<span style="color:#7f8c8d;">–</span>';
                }}

                // Render the trend table (previous vs. current Sollzins per Fixlaufzeit) and timestamp
                function renderTables(data, laufzeit) {{
                    const run = data.run;
                    const variations = data.variations;
                    const previousVariations = data.previous_variations || [];

                    const titleEl = document.getElementById('trend-table-title');
                    if (titleEl) {{
                        titleEl.textContent = '📊 Trend - Sollzins je Fixlaufzeit (' + laufzeit + ' Jahre Laufzeit)';
                    }}

                    const previousByFixierung = {{}};
                    previousVariations.forEach(v => {{ previousByFixierung[v.fixierung_jahre] = v.zinssatz; }});

                    const sortedVariations = [...variations].sort((a, b) => a.fixierung_jahre - b.fixierung_jahre);
                    let trendTable = '';
                    sortedVariations.forEach(v => {{
                        const currentStr = v.zinssatz;
                        const previousStr = previousByFixierung[v.fixierung_jahre];
                        const currentVal = parseSollzins(currentStr);
                        const previousVal = parseSollzins(previousStr);

                        let trend = 'na';
                        if (currentVal !== null && previousVal !== null) {{
                            if (Math.abs(currentVal - previousVal) < 0.005) trend = 'flat';
                            else if (currentVal > previousVal) trend = 'up';
                            else trend = 'down';
                        }}

                        trendTable += `
                                <tr>
                                    <td class="fixierung-cell">${{v.fixierung_jahre}}J</td>
                                    <td>${{formatSollzins(previousVal)}}</td>
                                    <td>${{formatSollzins(currentVal)}}</td>
                                    <td>${{trendBadge(trend)}}</td>
                                </tr>`;
                    }});
                    document.querySelector('#trend-tbody').innerHTML = trendTable;

                    // Update timestamp with run ID
                    const timestampDiv = document.querySelector('.timestamp');
                    const currentTime = timestampDiv.innerHTML.split('<br>')[0];
                    timestampDiv.innerHTML = currentTime + '<br>Data Source: Housing Loan Database | Run ID: ' + run.id +
                        '';
                }}
                
                // Laufzeit dropdown change handler
                document.getElementById('laufzeit-filter').addEventListener('change', function(e) {{
                    currentLaufzeit = e.target.value;
                    applyFilters();
                }});
                
                // Fixierung dropdown change handler
                document.getElementById('fixierung-filter').addEventListener('change', function(e) {{
                    currentFixierung = e.target.value;
                    applyFilters();
                }});
                
                // Zinssatz button click handler
                function setZinssatzFilter(type) {{
                    currentZinssatz = type;
                    
                    // Update button styling
                    document.getElementById('btn-beide').classList.remove('active');
                    document.getElementById('btn-zinssatz').classList.remove('active');
                    document.getElementById('btn-effektiver').classList.remove('active');
                    document.getElementById('btn-' + type).classList.add('active');
                    
                    applyFilters();
                }}
                
                // Mobile responsiveness for Plotly chart
                function handleResize() {{
                    const chartDiv = document.getElementById('plotly-chart');
                    if (chartDiv && chartDiv.data) {{
                        const isMobile = window.innerWidth <= 768;
                        const isSmallMobile = window.innerWidth <= 480;
                        
                        let newHeight = 600;
                        let newMargin = {{l: 80, r: 280, t: 80, b: 80}};
                        let showLegend = true;
                        
                        if (isSmallMobile) {{
                            newHeight = 300;
                            newMargin = {{l: 50, r: 50, t: 60, b: 60}};
                            showLegend = false;
                        }} else if (isMobile) {{
                            newHeight = 400;
                            newMargin = {{l: 60, r: 60, t: 70, b: 70}};
                            showLegend = false;
                        }}
                        
                        Plotly.relayout('plotly-chart', {{
                            height: newHeight,
                            margin: newMargin,
                            showlegend: showLegend
                        }});
                        // fig.to_html() wraps the graph div in a static outer <div
                        // style="height:600px">; Plotly.relayout only resizes the
                        // inner div/SVG, so without this the outer wrapper stays at
                        // its original height and leaves dead space below the chart.
                        if (chartDiv.parentElement) {{
                            chartDiv.parentElement.style.height = newHeight + 'px';
                        }}
                    }}
                }}
                
                // Add resize listener
                window.addEventListener('resize', handleResize);
                
                // Initial resize check
                setTimeout(handleResize, 1000);
                
                // Apply initial filters after chart loads
                setTimeout(() => {{
                    applyFilters();
                }}, 1500);
            </script>
        </div>
        

{generate_competitor_trend_charts_html(
    sollzins_chart_html,
    sollzins_fixierung_values,
    sollzins_table_html,
    effektivzins_chart_html,
    effektivzins_fixierung_values,
    effektivzins_table_html,
    lowest_offers_table_html
) if (sollzins_chart_html or effektivzins_chart_html) else ''}

        <!-- Angebotserfassung Formular -->
        <details class="accordion" style="margin-top: 32px;">
            <summary>➕ Neues Konkurrenzangebot erfassen</summary>
            <div class="accordion-body">
            <form id="offer-form" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px;">
                <div class="form-group">
                    <label for="anbieter" style="display: block; margin-bottom: 5px; font-weight: 600; color: #495057;">Bank/Anbieter *</label>
                    <input type="text" id="anbieter" name="anbieter" required
                           style="width: 100%; padding: 10px; border: 1px solid #ced4da; border-radius: 6px; font-size: 14px;"
                           placeholder="z.B. Raiffeisen, Volksbank...">
                </div>
                <div class="form-group">
                    <label for="angebotsdatum" style="display: block; margin-bottom: 5px; font-weight: 600; color: #495057;">Angebotsdatum *</label>
                    <input type="date" id="angebotsdatum" name="angebotsdatum" required
                           style="width: 100%; padding: 10px; border: 1px solid #ced4da; border-radius: 6px; font-size: 14px;">
                </div>
                <div class="form-group">
                    <label for="fixzinssatz" style="display: block; margin-bottom: 5px; font-weight: 600; color: #495057;">Fixzinssatz (%)</label>
                    <input type="number" id="fixzinssatz" name="fixzinssatz" step="0.001" min="0" max="20"
                           style="width: 100%; padding: 10px; border: 1px solid #ced4da; border-radius: 6px; font-size: 14px;"
                           placeholder="z.B. 3.250">
                </div>
                <div class="form-group">
                    <label for="effektivzinssatz" style="display: block; margin-bottom: 5px; font-weight: 600; color: #495057;">Effektivzinssatz (%)</label>
                    <input type="number" id="effektivzinssatz" name="effektivzinssatz" step="0.001" min="0" max="20"
                           style="width: 100%; padding: 10px; border: 1px solid #ced4da; border-radius: 6px; font-size: 14px;"
                           placeholder="z.B. 3.450">
                </div>
                <div class="form-group">
                    <label for="laufzeit" style="display: block; margin-bottom: 5px; font-weight: 600; color: #495057;">Laufzeit (Jahre)</label>
                    <input type="number" id="laufzeit" name="laufzeit" min="1" max="40"
                           style="width: 100%; padding: 10px; border: 1px solid #ced4da; border-radius: 6px; font-size: 14px;"
                           placeholder="z.B. 25">
                </div>
                <div class="form-group">
                    <label for="fixzinssatz_in_jahren" style="display: block; margin-bottom: 5px; font-weight: 600; color: #495057;">Fixlaufzeit (Jahre)</label>
                    <input type="number" id="fixzinssatz_in_jahren" name="fixzinssatz_in_jahren" min="0" max="40"
                           style="width: 100%; padding: 10px; border: 1px solid #ced4da; border-radius: 6px; font-size: 14px;"
                           placeholder="z.B. 10">
                </div>
                <div class="form-group" style="grid-column: 1 / -1; display: flex; gap: 15px; align-items: center;">
                    <button type="submit" id="submit-btn"
                            style="padding: 12px 30px; background: linear-gradient(135deg, #28a745 0%, #218838 100%); color: white; border: none; border-radius: 6px; font-size: 16px; font-weight: 600; cursor: pointer; transition: transform 0.2s, box-shadow 0.2s;">
                        💾 Angebot speichern
                    </button>
                    <span id="form-status" style="color: #6c757d; font-size: 14px;"></span>
                </div>
            </form>
            </div>
        </details>

        <script>
            // Offer form submission handler
            document.getElementById('offer-form').addEventListener('submit', async function(e) {{
                e.preventDefault();

                const submitBtn = document.getElementById('submit-btn');
                const statusSpan = document.getElementById('form-status');

                submitBtn.disabled = true;
                submitBtn.textContent = '⏳ Speichern...';
                statusSpan.textContent = '';

                const formData = new FormData(e.target);
                const data = Object.fromEntries(formData.entries());

                try {{
                    const response = await fetch('{OFFER_API_URL}', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify(data)
                    }});

                    const result = await response.json();

                    if (response.ok) {{
                        statusSpan.style.color = '#28a745';
                        statusSpan.textContent = '✅ ' + result.message + ' (ID: ' + result.id + ')';
                        e.target.reset();
                        // Set today's date as default
                        document.getElementById('angebotsdatum').valueAsDate = new Date();
                    }} else {{
                        statusSpan.style.color = '#dc3545';
                        statusSpan.textContent = '❌ Fehler: ' + result.message;
                    }}
                }} catch (error) {{
                    console.error('API Error:', error);
                    statusSpan.style.color = '#dc3545';
                    statusSpan.textContent = '❌ Fehler: ' + error.message;
                }}

                submitBtn.disabled = false;
                submitBtn.textContent = '💾 Angebot speichern';
            }});

            // Set today's date as default
            document.getElementById('angebotsdatum').valueAsDate = new Date();
        </script>

'''

    # Add SWAP/Euribor section first (Marktzinsen above OeNB), then OeNB
    swap_euribor_section_html = generate_swap_euribor_section_html(
        swap_chart_html, euribor_chart_html, swap_png_base64, euribor_png_base64,
        for_email=False, swap_maturities=swap_maturities, swap_table_html=swap_table_html
    )
    html_content += swap_euribor_section_html

    oenb_section_html = generate_oenb_section_html(oenb_screenshots)
    html_content += oenb_section_html

    html_content += f'''
        <div class="timestamp">
            Last Updated: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}<br>
            Data Source: Housing Loan Database | Latest Run ID: {latest_run['id']}<br>
        </div>
    </div>
</body>
</html>
'''
    
    # Write to file
    with open(HTML_PATH, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"[OK] HTML page generated: {HTML_PATH}")
    return True, png_base64, sollzins_png_base64, effektivzins_png_base64


def generate_email_html(png_base64, sollzins_png_base64=None, effektivzins_png_base64=None):
    """
    Generate static HTML for email (no JavaScript, so no filter accordions,
    interactive Plotly charts, or the competitor-offer entry form). Mirrors
    the redesigned web page's structure/section order as closely as an
    email-safe rendering allows: Durchblicker chart + trend table,
    Konkurrenzangebote trend charts (Sollzins + Effektivzins) + lowest-offers-last-30-days table, then
    Marktzinsen (SWAP/Euribor) before OeNB, using the same shared
    section-rendering functions as generate_html() so both stay in sync.
    """

    if not png_base64:
        print("[WARN] No PNG data available, cannot generate email HTML")
        return False

    # Get all runs data
    runs, all_variations = get_all_runs_data()

    if not runs:
        print("[WARN] No data found in database")
        return False

    # Get latest OeNB screenshots
    oenb_screenshots = get_latest_oenb_screenshots()

    # Generate SWAP/Euribor charts for email
    print("[INFO] Generating SWAP/Euribor charts for email...")
    swap_chart_result = generate_swap_rates_chart()
    euribor_chart_result = generate_euribor_chart()

    if swap_chart_result[0]:
        swap_chart_html, swap_maturities, swap_png_base64, swap_table_html = swap_chart_result
    else:
        swap_chart_html, swap_maturities, swap_png_base64, swap_table_html = None, [], None, ''

    if euribor_chart_result[0]:
        euribor_chart_html, euribor_png_base64 = euribor_chart_result
    else:
        euribor_chart_html, euribor_png_base64 = None, None

    # Generate tables for last 5 months from competitor data
    try:
        from competitor_trend_charts import get_monthly_competitor_stats, generate_last_5_months_table_html
        sollzins_stats_10y, effektivzins_stats_10y = get_monthly_competitor_stats(DB_PATH, fixierung_filter=10)
        sollzins_table_html = generate_last_5_months_table_html(sollzins_stats_10y, "Sollzinssatz") if sollzins_stats_10y else ''
        effektivzins_table_html = generate_last_5_months_table_html(effektivzins_stats_10y, "Effektivzinssatz") if effektivzins_stats_10y else ''
    except Exception as e:
        print(f"[WARN] Could not generate 5-month tables for email: {e}")
        sollzins_table_html = ''
        effektivzins_table_html = ''

    # Lowest Sollzins per bank in the last 30 days, for the table under the
    # Konkurrenzangebote chart (same helper as the web page)
    try:
        lowest_offers_table_html = generate_lowest_offers_table_html(get_all_loan_offers(), days=30)
    except Exception as e:
        print(f"[WARN] Could not build lowest-offers table for email: {e}")
        lowest_offers_table_html = ''

    # Get 25J run for the trend table (default), same as the web page's
    # initial state
    latest_run = None
    latest_variations = None

    for run in runs:
        if run['laufzeit_jahre'] == 25:
            latest_run = run
            latest_variations = all_variations[run['id']]
            break

    if not latest_run:
        latest_run = runs[0]
        latest_variations = all_variations[latest_run['id']]

    # Trend table: current vs. previous run (at least 6 days apart) for the
    # same Laufzeit as latest_run, same logic as generate_html()
    same_laufzeit_runs = [
        {'run': run, 'variations': all_variations[run['id']]}
        for run in runs if run['laufzeit_jahre'] == latest_run['laufzeit_jahre']
    ]
    same_laufzeit_runs.sort(key=lambda x: x['run']['scrape_date'], reverse=True)
    previous_run_data = find_previous_run(same_laufzeit_runs, min_gap_days=6)
    trend_rows = compute_trend_rows(
        latest_variations, previous_run_data['variations'] if previous_run_data else None
    )
    trend_tbody_html = ''.join(
        f'''
                        <tr>
                            <td class="fixierung-cell">{row['fixierung_jahre']}J</td>
                            <td>{row['previous_short']}</td>
                            <td>{row['current_short']}</td>
                            <td>{trend_badge_html(row['trend'])}</td>
                        </tr>'''
        for row in trend_rows
    )

    # Create static HTML content for email (no JavaScript) - same design
    # tokens and section markup as generate_html(), minus anything
    # JS-dependent (filter accordions, Plotly, the offer-entry form)
    html_content = f'''<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bank Comparison - Housing Loan Analysis</title>
    <style>
        :root {{
            --color-bg: #f2f5f7;
            --color-surface: #ffffff;
            --color-primary: #0f3b52;
            --color-primary-dark: #0a2b3d;
            --color-accent: #0a8a9a;
            --color-accent-light: #e3f4f6;
            --color-text: #1b2733;
            --color-text-muted: #5b6b78;
            --color-border: #e2e8ee;
            --radius-sm: 8px;
            --radius-md: 12px;
            --radius-lg: 16px;
            --shadow-sm: 0 1px 3px rgba(15, 59, 82, 0.08);
            --shadow-md: 0 6px 20px rgba(15, 59, 82, 0.09);
            --font-sans: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
        }}
        * {{
            box-sizing: border-box;
        }}
        body {{
            font-family: var(--font-sans);
            margin: 0;
            padding: 20px;
            background: var(--color-bg);
            color: var(--color-text);
            min-height: 100vh;
        }}
        .interactive-button {{
            display: block;
            width: fit-content;
            margin: 25px auto;
            padding: 15px 30px;
            background-color: #0f3b52 !important;
            color: white !important;
            text-decoration: none !important;
            border-radius: 8px;
            font-size: 1.1em;
            font-weight: bold;
            text-align: center;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .interactive-button:visited, .interactive-button:link {{
            color: white !important;
            text-decoration: none !important;
            background-color: #0f3b52 !important;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background-color: var(--color-surface);
            padding: 30px;
            border-radius: var(--radius-lg);
            box-shadow: var(--shadow-md);
        }}
        h1 {{
            color: var(--color-primary);
            text-align: center;
            margin-bottom: 10px;
            font-size: 2.0em;
            font-weight: 700;
        }}
        h2 {{
            color: var(--color-primary);
            font-size: 1.25em;
            margin-bottom: 15px;
            font-weight: 700;
        }}
        .subtitle {{
            text-align: center;
            color: var(--color-text-muted);
            margin-bottom: 30px;
            font-size: 1.05em;
        }}
        .chart-container {{
            margin-bottom: 40px;
            padding: 24px;
            background: var(--color-surface);
            border: 1px solid var(--color-border);
            border-radius: var(--radius-lg);
            box-shadow: var(--shadow-sm);
        }}
        .chart-container img {{
            max-width: 100%;
            height: auto;
            border-radius: 8px;
        }}
        .chart-title {{
            font-size: 1.2em;
            font-weight: 700;
            color: var(--color-primary);
            margin: 0 0 16px;
        }}
        .table-container {{
            overflow-x: auto;
            margin-bottom: 24px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 16px;
            font-size: 0.9em;
        }}
        th {{
            background: var(--color-primary);
            color: white;
            padding: 12px;
            text-align: left;
            font-weight: 600;
        }}
        td {{
            padding: 11px 12px;
            border-bottom: 1px solid var(--color-border);
        }}
        tr:nth-child(even) {{
            background-color: #f8fafb;
        }}
        .fixierung-cell {{
            font-weight: 700;
            color: var(--color-primary);
            background-color: var(--color-accent-light) !important;
            border-left: 4px solid var(--color-accent);
        }}
        .rate-cell {{
            font-weight: 700;
            color: var(--color-primary);
            font-size: 1.05em;
        }}
        .timestamp {{
            text-align: center;
            color: var(--color-text-muted);
            font-size: 0.85em;
            margin-top: 28px;
            padding-top: 18px;
            border-top: 1px solid var(--color-border);
        }}
        @media (max-width: 768px) {{
            body {{
                padding: 5px;
            }}
            .container {{
                padding: 10px;
                border-radius: 0;
                box-shadow: none;
            }}
            h1 {{
                font-size: 1.4em;
            }}
            h2, .chart-title {{
                font-size: 1.0em !important;
            }}
            .chart-container {{
                padding: 12px;
            }}
            table {{
                font-size: 11px;
                min-width: 450px;
            }}
            th, td {{
                padding: 8px 4px;
                white-space: nowrap;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🏠 Housing Loan Comparison</h1>
        <div class="subtitle">
            Sollzins-Entwicklung - 25 Jahre Laufzeit
        </div>

        <a href="https://smartprototypes.net/Bank_market_overview/bank_comparison_housing_loan_durchblicker.html" class="interactive-button" target="_blank">
            🔗 Zu den interaktiven Charts
        </a>

        <div class="chart-container">
            <div class="chart-title">📈 Wohnkredite - Durchblicker-Bestpreis</div>
            <img src="data:image/png;base64,{png_base64}" alt="Housing Loan Interest Rate Chart">

            <div class="table-container" style="margin-top: 24px;">
                <h2>📊 Trend - Sollzins je Fixlaufzeit ({latest_run['laufzeit_jahre']} Jahre Laufzeit)</h2>
                <table>
                    <thead>
                        <tr>
                            <th>FixLZ</th>
                            <th>Voriger Lauf</th>
                            <th>Aktueller Lauf</th>
                            <th>Trend</th>
                        </tr>
                    </thead>
                    <tbody>{trend_tbody_html}
                    </tbody>
                </table>
            </div>
        </div>


{f'''
        <!-- Sollzinssatz Competitor Trend (Email) -->
        <div class="chart-container" style="margin-top: 40px;">
            <h2 style="color: #1b2733; font-size: 20px; margin-bottom: 16px;">📊 Sollzinssatz Konkurrenzangebote - Zeitverlauf (10 Jahre)</h2>
            <div style="text-align: center; margin: 20px 0;">
                <img src="data:image/png;base64,{sollzins_png_base64}"
                     alt="Sollzins Trend Chart"
                     style="max-width: 100%; height: auto; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
            </div>
{sollzins_table_html}
        </div>
''' if sollzins_png_base64 else ''}

{f'''
        <!-- Effektivzinssatz Competitor Trend (Email) -->
        <div class="chart-container" style="margin-top: 40px;">
            <h2 style="color: #1b2733; font-size: 20px; margin-bottom: 16px;">📈 Effektivzinssatz Konkurrenzangebote - Zeitverlauf (10 Jahre)</h2>
            <div style="text-align: center; margin: 20px 0;">
                <img src="data:image/png;base64,{effektivzins_png_base64}"
                     alt="Effektivzins Trend Chart"
                     style="max-width: 100%; height: auto; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
            </div>
{effektivzins_table_html}
{lowest_offers_table_html}
        </div>
''' if effektivzins_png_base64 else ''}
'''

    # Add SWAP/Euribor section first (Marktzinsen above OeNB), then OeNB -
    # same order as generate_html()
    swap_euribor_section_html = generate_swap_euribor_section_html(
        swap_chart_html, euribor_chart_html, swap_png_base64, euribor_png_base64, for_email=True,
        swap_table_html=swap_table_html
    )
    html_content += swap_euribor_section_html

    oenb_section_html = generate_oenb_section_html(oenb_screenshots, for_email=True)
    html_content += oenb_section_html

    html_content += f'''
        <div class="timestamp">
            Last Updated: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}<br>
            Data Source: Housing Loan Database | Latest Run ID: {latest_run['id']}<br>
        </div>
    </div>
</body>
</html>
'''

    # Write to file
    with open(HTML_EMAIL_PATH, 'w', encoding='utf-8') as f:
        f.write(html_content)

    print(f"[OK] Email HTML page generated: {HTML_EMAIL_PATH}")
    return True


if __name__ == "__main__":
    print("\n" + "="*60)
    print("Generating Housing Loan HTML Report (Interactive Plotly)")
    print("="*60 + "\n")
    
    # Check if view exists
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='view' AND name='housing_loan_chart_ready'")
    view_exists = cursor.fetchone()
    conn.close()
    
    if not view_exists:
        print("[WARN] View 'housing_loan_chart_ready' does not exist!")
        print("   Please run: python3 create_housing_loan_view.py")
        exit(1)
    
    # Generate interactive HTML (for website)
    print("[INFO] Generating interactive HTML for web...")
    success, png_base64, sollzins_png_base64, effektivzins_png_base64 = generate_html()
    
    if success:
        print("\n[SUCCESS] Interactive HTML report generated successfully!")
        print(f"   [FILE] Web HTML: {HTML_PATH}")
        print(f"   [FILE] Chart PNG: {CHART_PNG_PATH}")
        if sollzins_png_base64:
            print(f"   [INFO] Sollzins Competitor Trend Chart PNG generated")
        if effektivzins_png_base64:
            print(f"   [INFO] Effektivzins Competitor Trend Chart PNG generated")
        
        # Generate email HTML (with static PNGs)
        print("\n[INFO] Generating email-friendly HTML...")
        email_success = generate_email_html(png_base64, sollzins_png_base64, effektivzins_png_base64)
        
        if email_success:
            print("\n[SUCCESS] Email HTML report generated successfully!")
            print(f"   [FILE] Email HTML: {HTML_EMAIL_PATH}")
        else:
            print("\n[WARN] Email HTML generation failed (continuing anyway)")
        
        print(f"\n   Open in browser: file://{HTML_PATH.absolute()}")
        print("\n   [FEATURES] Web Version Features:")
        print("      • Laufzeit dropdown filter (All, 15, 20, 25, 30 Jahre)")
        print("      • Toggle Zinssatz / Effektiver Zinssatz")
        print("      • Interactive legend (click to show/hide)")
        print("      • Zoom, pan, hover for details")
        print("\n   [FEATURES] Email Version Features:")
        print("      • Static PNG chart (works in all email clients)")
        print("      • No JavaScript required")
        print("      • Embedded base64 image")
    else:
        print("\n[ERROR] HTML generation failed!")
