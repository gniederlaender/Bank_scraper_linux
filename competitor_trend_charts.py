#!/usr/bin/env python3
"""
Competitor Trend Charts for Housing Loan Comparison

Generates two time-series charts based on manually entered competitor offers:
1. Sollzinssatz (Fixed Interest Rate) - Min and Median over time
2. Effektivzinssatz (Effective Interest Rate) - Min and Median over time

Both charts are filterable by Fixlaufzeit (0J, 5J, 10J, 15J, 20J, 25J)
"""

import sqlite3
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import statistics
from collections import defaultdict
import plotly.graph_objects as go
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import base64
from io import BytesIO


def parse_sollzins(sollzins_str: str) -> Optional[float]:
    """
    Parse Sollzins from various string formats to float.
    Examples: "3,150%" -> 3.150, "3,66 %" -> 3.66, "3.5%" -> 3.5
    """
    if not sollzins_str or sollzins_str.strip() in ['', 'None', 'nicht angegeben', '-']:
        return None

    clean = sollzins_str.replace('%', '').replace('p.a.', '').strip()
    clean = clean.replace(',', '.')

    try:
        return float(clean)
    except ValueError:
        match = re.search(r'(\d+[.,]\d+)', sollzins_str)
        if match:
            value = match.group(1).replace(',', '.')
            return float(value)
    return None


def parse_date(date_str: str) -> Optional[datetime]:
    """Parse date from DD.MM.YYYY format."""
    if not date_str or date_str.strip() in ['', 'None', 'nicht angegeben', '-']:
        return None

    try:
        return datetime.strptime(date_str.strip(), '%d.%m.%Y')
    except ValueError:
        return None


def normalize_fixierung(fixierung_str: str) -> Optional[int]:
    """
    Normalize fixierung strings to integer years.
    Examples: "10" -> 10, "10 Jahre" -> 10
    """
    if not fixierung_str or fixierung_str.strip() in ['', 'None', 'nicht angegeben', '-']:
        return None

    match = re.search(r'(\d+)', fixierung_str)
    if match:
        return int(match.group(1))
    return None


def get_monthly_competitor_stats(
    db_path: Path,
    fixierung_filter: Optional[int] = None
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Get monthly statistics for competitor offers.

    Returns:
        Tuple of (sollzins_stats, effektivzins_stats)
        Each is a list of dicts with: month, min, median, count
    """
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Get all loan offers with fixierung info
    cursor.execute("""
        SELECT
            anbieter,
            angebotsdatum,
            COALESCE(fixzinssatz, sollzinssatz) as sollzins,
            effektivzinssatz,
            fixzinssatz_in_jahren,
            laufzeit
        FROM loan_offers
        WHERE angebotsdatum IS NOT NULL
          AND angebotsdatum NOT IN ('', 'nicht angegeben', '-', 'None')
        ORDER BY angebotsdatum
    """)

    rows = cursor.fetchall()
    conn.close()

    # Group by month
    monthly_sollzins = defaultdict(list)
    monthly_effektivzins = defaultdict(list)

    for anbieter, datum_str, sollzins_str, effektivzins_str, fixierung_str, laufzeit in rows:
        datum = parse_date(datum_str)
        if datum is None:
            continue

        fixierung_norm = normalize_fixierung(fixierung_str)

        # Apply fixierung filter if specified
        if fixierung_filter is not None and fixierung_norm != fixierung_filter:
            continue

        month = datum.strftime('%Y-%m')

        # Parse sollzins
        sollzins = parse_sollzins(sollzins_str)
        if sollzins is not None:
            monthly_sollzins[month].append(sollzins)

        # Parse effektivzins
        effektivzins = parse_sollzins(effektivzins_str)
        if effektivzins is not None:
            monthly_effektivzins[month].append(effektivzins)

    # Calculate statistics
    sollzins_stats = []
    for month in sorted(monthly_sollzins.keys()):
        values = monthly_sollzins[month]
        if values:
            sollzins_stats.append({
                'month': month,
                'min': min(values),
                'median': statistics.median(values),
                'count': len(values)
            })

    effektivzins_stats = []
    for month in sorted(monthly_effektivzins.keys()):
        values = monthly_effektivzins[month]
        if values:
            effektivzins_stats.append({
                'month': month,
                'min': min(values),
                'median': statistics.median(values),
                'count': len(values)
            })

    return sollzins_stats, effektivzins_stats


def get_all_fixierung_values(db_path: Path) -> List[int]:
    """Get all unique fixierung values from loan_offers."""
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT fixzinssatz_in_jahren
        FROM loan_offers
        WHERE fixzinssatz_in_jahren IS NOT NULL
          AND fixzinssatz_in_jahren NOT IN ('', 'nicht angegeben', '-', 'None')
    """)

    rows = cursor.fetchall()
    conn.close()

    fixierung_values = set()
    for (fixierung_str,) in rows:
        fixierung = normalize_fixierung(fixierung_str)
        if fixierung is not None:
            fixierung_values.add(fixierung)

    return sorted(list(fixierung_values))


def generate_competitor_sollzins_chart(
    db_path: Path,
    plotly_font: str = 'Arial',
    color_primary: str = '#0f3b52',
    color_accent: str = '#0a8a9a',
    color_text: str = '#1b2733',
    color_grid: str = '#e2e8ee'
) -> Tuple[Optional[str], List[int], Optional[Dict]]:
    """
    Generate interactive Plotly chart for Sollzinssatz trends.

    Returns:
        (chart_html, fixierung_values, all_data_by_fixierung)
    """
    fixierung_values = get_all_fixierung_values(db_path)

    if not fixierung_values:
        print("[WARN] No fixierung values found in competitor offers")
        return None, [], None

    # Get data for all fixierung values
    all_data = {}
    for fixierung in fixierung_values:
        sollzins_stats, _ = get_monthly_competitor_stats(db_path, fixierung)
        if sollzins_stats:
            all_data[fixierung] = sollzins_stats

    if not all_data:
        print("[WARN] No sollzins data found")
        return None, fixierung_values, None

    # Create figure
    fig = go.Figure()

    # Add traces for each fixierung
    for fixierung in sorted(all_data.keys()):
        stats = all_data[fixierung]
        months = [s['month'] for s in stats]
        min_values = [s['min'] for s in stats]
        median_values = [s['median'] for s in stats]

        # Convert month strings to dates for plotting
        dates = [datetime.strptime(m, '%Y-%m') for m in months]

        # Default: only show 10J, hide others
        is_visible = (fixierung == 10)

        # Min line
        fig.add_trace(go.Scatter(
            x=dates,
            y=min_values,
            mode='lines+markers',
            name=f'{fixierung}J - Min',
            line=dict(width=2, dash='solid'),
            marker=dict(size=8),
            hovertemplate='<b>%{x|%B %Y}</b><br>Min: %{y:.3f}%<extra></extra>',
            visible=is_visible,
            customdata=[[fixierung, 'min']] * len(dates)
        ))

        # Median line
        fig.add_trace(go.Scatter(
            x=dates,
            y=median_values,
            mode='lines+markers',
            name=f'{fixierung}J - Median',
            line=dict(width=2, dash='dash'),
            marker=dict(size=8, symbol='diamond'),
            hovertemplate='<b>%{x|%B %Y}</b><br>Median: %{y:.3f}%<extra></extra>',
            visible=is_visible,
            customdata=[[fixierung, 'median']] * len(dates)
        ))

    # Update layout
    fig.update_layout(
        title={
            'text': '📊 Sollzinssatz Konkurrenzangebote - Zeitverlauf',
            'x': 0.5,
            'xanchor': 'center',
            'font': {'size': 18, 'family': plotly_font, 'color': color_text}
        },
        xaxis=dict(
            title='Monat',
            showgrid=True,
            gridcolor=color_grid,
            tickformat='%b %Y'
        ),
        yaxis=dict(
            title='Sollzinssatz (%)',
            showgrid=True,
            gridcolor=color_grid
        ),
        hovermode='closest',
        plot_bgcolor='white',
        paper_bgcolor='white',
        font=dict(family=plotly_font, size=12, color=color_text),
        legend=dict(
            orientation="v",
            yanchor="top",
            y=1,
            xanchor="left",
            x=1.02,
            bgcolor="rgba(255,255,255,0.8)",
            bordercolor=color_grid,
            borderwidth=1
        ),
        height=500,
        margin=dict(l=80, r=200, t=80, b=80)
    )

    # Convert to HTML
    chart_html = fig.to_html(
        include_plotlyjs='cdn',
        div_id='plotly-competitor-sollzins-chart',
        config={
            'displayModeBar': True,
            'displaylogo': False,
            'modeBarButtonsToRemove': ['select2d', 'lasso2d'],
            'toImageButtonOptions': {
                'format': 'png',
                'filename': 'competitor_sollzins_trend',
                'height': 600,
                'width': 1200,
                'scale': 2
            },
            'responsive': True
        }
    )

    # Generate table for last 5 months (10J data only)
    table_html = ''
    if 10 in all_data:
        table_html = generate_last_5_months_table_html(all_data[10], "Sollzinssatz")

    return chart_html, fixierung_values, all_data, table_html


def generate_competitor_effektivzins_chart(
    db_path: Path,
    plotly_font: str = 'Arial',
    color_primary: str = '#0f3b52',
    color_accent: str = '#0a8a9a',
    color_text: str = '#1b2733',
    color_grid: str = '#e2e8ee'
) -> Tuple[Optional[str], List[int], Optional[Dict]]:
    """
    Generate interactive Plotly chart for Effektivzinssatz trends.

    Returns:
        (chart_html, fixierung_values, all_data_by_fixierung)
    """
    fixierung_values = get_all_fixierung_values(db_path)

    if not fixierung_values:
        print("[WARN] No fixierung values found in competitor offers")
        return None, [], None

    # Get data for all fixierung values
    all_data = {}
    for fixierung in fixierung_values:
        _, effektivzins_stats = get_monthly_competitor_stats(db_path, fixierung)
        if effektivzins_stats:
            all_data[fixierung] = effektivzins_stats

    if not all_data:
        print("[WARN] No effektivzins data found")
        return None, fixierung_values, None

    # Create figure
    fig = go.Figure()

    # Add traces for each fixierung
    for fixierung in sorted(all_data.keys()):
        stats = all_data[fixierung]
        months = [s['month'] for s in stats]
        min_values = [s['min'] for s in stats]
        median_values = [s['median'] for s in stats]

        # Convert month strings to dates for plotting
        dates = [datetime.strptime(m, '%Y-%m') for m in months]

        # Default: only show 10J, hide others
        is_visible = (fixierung == 10)

        # Min line
        fig.add_trace(go.Scatter(
            x=dates,
            y=min_values,
            mode='lines+markers',
            name=f'{fixierung}J - Min',
            line=dict(width=2, dash='solid'),
            marker=dict(size=8),
            hovertemplate='<b>%{x|%B %Y}</b><br>Min: %{y:.3f}%<extra></extra>',
            visible=is_visible,
            customdata=[[fixierung, 'min']] * len(dates)
        ))

        # Median line
        fig.add_trace(go.Scatter(
            x=dates,
            y=median_values,
            mode='lines+markers',
            name=f'{fixierung}J - Median',
            line=dict(width=2, dash='dash'),
            marker=dict(size=8, symbol='diamond'),
            hovertemplate='<b>%{x|%B %Y}</b><br>Median: %{y:.3f}%<extra></extra>',
            visible=is_visible,
            customdata=[[fixierung, 'median']] * len(dates)
        ))

    # Update layout
    fig.update_layout(
        title={
            'text': '📈 Effektivzinssatz Konkurrenzangebote - Zeitverlauf',
            'x': 0.5,
            'xanchor': 'center',
            'font': {'size': 18, 'family': plotly_font, 'color': color_text}
        },
        xaxis=dict(
            title='Monat',
            showgrid=True,
            gridcolor=color_grid,
            tickformat='%b %Y'
        ),
        yaxis=dict(
            title='Effektivzinssatz (%)',
            showgrid=True,
            gridcolor=color_grid
        ),
        hovermode='closest',
        plot_bgcolor='white',
        paper_bgcolor='white',
        font=dict(family=plotly_font, size=12, color=color_text),
        legend=dict(
            orientation="v",
            yanchor="top",
            y=1,
            xanchor="left",
            x=1.02,
            bgcolor="rgba(255,255,255,0.8)",
            bordercolor=color_grid,
            borderwidth=1
        ),
        height=500,
        margin=dict(l=80, r=200, t=80, b=80)
    )

    # Convert to HTML
    chart_html = fig.to_html(
        include_plotlyjs='cdn',
        div_id='plotly-competitor-effektivzins-chart',
        config={
            'displayModeBar': True,
            'displaylogo': False,
            'modeBarButtonsToRemove': ['select2d', 'lasso2d'],
            'toImageButtonOptions': {
                'format': 'png',
                'filename': 'competitor_effektivzins_trend',
                'height': 600,
                'width': 1200,
                'scale': 2
            },
            'responsive': True
        }
    )

    # Generate table for last 5 months (10J data only)
    table_html = ''
    if 10 in all_data:
        table_html = generate_last_5_months_table_html(all_data[10], "Effektivzinssatz")

    return chart_html, fixierung_values, all_data, table_html


def generate_static_png_competitor_sollzins(all_data: Dict[int, List[Dict]], output_path: Optional[Path] = None) -> str:
    """
    Generate static PNG chart for Sollzinssatz (for email).
    Only shows 10 Jahre Fixierung data.

    Returns:
        base64-encoded PNG string
    """
    if not all_data or 10 not in all_data:
        return None

    # Only use 10J data
    stats = all_data[10]

    fig, ax = plt.subplots(figsize=(12, 6))

    months = [datetime.strptime(s['month'], '%Y-%m') for s in stats]
    min_values = [s['min'] for s in stats]
    median_values = [s['median'] for s in stats]

    # Min line
    ax.plot(months, min_values,
            marker='o', linestyle='-', linewidth=2,
            color='#d97706', label='10J - Niedrigster')

    # Median line
    ax.plot(months, median_values,
            marker='D', linestyle='--', linewidth=2,
            color='#d97706', alpha=0.7, label='10J - Median')

    ax.set_xlabel('Monat', fontsize=12)
    ax.set_ylabel('Sollzinssatz (%)', fontsize=12)
    ax.set_title('Sollzinssatz Konkurrenzangebote - Zeitverlauf', fontsize=14, fontweight='bold')
    ax.grid(True, alpha=0.3)
    ax.legend(loc='best', fontsize=9)

    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
    plt.xticks(rotation=45)

    plt.tight_layout()

    # Save to bytes buffer
    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close()

    # Optionally save to file
    if output_path:
        with open(output_path, 'wb') as f:
            f.write(buf.getvalue())
        buf.seek(0)

    return base64.b64encode(buf.read()).decode('utf-8')


def generate_last_5_months_table_html(data: List[Dict], rate_type: str = "Sollzinssatz") -> str:
    """
    Generate HTML table for last 5 months of data.

    Args:
        data: List of monthly statistics (month, min, median, count)
        rate_type: "Sollzinssatz" or "Effektivzinssatz"

    Returns:
        HTML string for the table
    """
    if not data:
        return '<p style="text-align: center; color: #666; padding: 20px;">Keine Daten verfügbar</p>'

    # Get last 5 months
    last_5 = data[-5:] if len(data) >= 5 else data

    # Format month names
    def format_month(month_str):
        try:
            dt = datetime.strptime(month_str, '%Y-%m')
            # German month names
            month_names = ['Jän', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun',
                          'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']
            return f"{month_names[dt.month-1]} {dt.year}"
        except:
            return month_str

    rows_html = '\n'.join([
        f'''                        <tr>
                            <td style="padding: 12px; text-align: left; border-bottom: 1px solid #eee;">{format_month(item['month'])}</td>
                            <td style="padding: 12px; text-align: left; border-bottom: 1px solid #eee;">{item['min']:.3f}%</td>
                            <td style="padding: 12px; text-align: left; border-bottom: 1px solid #eee;">{item['median']:.3f}%</td>
                        </tr>'''
        for item in last_5
    ])

    return f'''
            <div class="table-container" style="margin-top: 24px;">
                <h3 style="margin-bottom: 16px; font-size: 16px; color: #1b2733;">📊 Entwicklung letzte 5 Monate - {rate_type} (10J Fixlaufzeit)</h3>
                <table style="width: 100%; border-collapse: collapse;">
                    <thead>
                        <tr style="background-color: #f5f5f5;">
                            <th style="padding: 12px; text-align: left; border-bottom: 2px solid #ddd;">Monat</th>
                            <th style="padding: 12px; text-align: left; border-bottom: 2px solid #ddd;">Niedrigster</th>
                            <th style="padding: 12px; text-align: left; border-bottom: 2px solid #ddd;">Median</th>
                        </tr>
                    </thead>
                    <tbody>
{rows_html}
                    </tbody>
                </table>
            </div>'''


def generate_static_png_competitor_effektivzins(all_data: Dict[int, List[Dict]], output_path: Optional[Path] = None) -> str:
    """
    Generate static PNG chart for Effektivzinssatz (for email).
    Only shows 10 Jahre Fixierung data.

    Returns:
        base64-encoded PNG string
    """
    if not all_data or 10 not in all_data:
        return None

    # Only use 10J data
    stats = all_data[10]

    fig, ax = plt.subplots(figsize=(12, 6))

    months = [datetime.strptime(s['month'], '%Y-%m') for s in stats]
    min_values = [s['min'] for s in stats]
    median_values = [s['median'] for s in stats]

    # Min line
    ax.plot(months, min_values,
            marker='o', linestyle='-', linewidth=2,
            color='#059669', label='10J - Niedrigster')

    # Median line
    ax.plot(months, median_values,
            marker='D', linestyle='--', linewidth=2,
            color='#059669', alpha=0.7, label='10J - Median')

    ax.set_xlabel('Monat', fontsize=12)
    ax.set_ylabel('Effektivzinssatz (%)', fontsize=12)
    ax.set_title('Effektivzinssatz Konkurrenzangebote - Zeitverlauf', fontsize=14, fontweight='bold')
    ax.grid(True, alpha=0.3)
    ax.legend(loc='best', fontsize=9)

    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
    plt.xticks(rotation=45)

    plt.tight_layout()

    # Save to bytes buffer
    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close()

    # Optionally save to file
    if output_path:
        with open(output_path, 'wb') as f:
            f.write(buf.getvalue())
        buf.seek(0)

    return base64.b64encode(buf.read()).decode('utf-8')
