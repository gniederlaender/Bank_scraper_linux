#!/usr/bin/env python3
"""
Generate HTML page with interactive Plotly charts for housing loan data from durchblicker.at
"""

import sqlite3
import os
from datetime import datetime
from pathlib import Path
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import json
import base64
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from db_helper import get_all_loan_offers
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
    
    # Specific bank colors
    if 'bank austria' in anbieter_lower or 'unicredit' in anbieter_lower:
        return '#FF0000'  # Red
    elif 'volksbank' in anbieter_lower:
        return '#0000FF'  # Blue
    elif 'raiffeisen' in anbieter_lower:
        return '#FFFF00'  # Yellow
    elif 'sparkasse' in anbieter_lower:
        return '#87CEEB'  # Light Blue (Sky Blue) - for all Sparkasse banks
    
    # Default colors for other banks
    default_colors = [
        '#FFA500',  # Orange
        '#FF69B4',  # Hot Pink
        '#32CD32',  # Lime Green
        '#1E90FF',  # Dodger Blue
        '#9370DB',  # Medium Purple
        '#FF1493',  # Deep Pink
        '#00CED1',  # Dark Turquoise
        '#FFD700',  # Gold
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
    
    # Convert timestamp to datetime
    df['scrape_timestamp'] = pd.to_datetime(df['scrape_timestamp'])
    
    # Define colors for each Fixierung variation (years)
    colors = {
        0: '#1f77b4',   # Blue
        5: '#2ca02c',   # Green
        10: '#ff7f0e',  # Orange
        15: '#d62728',  # Red
        20: '#9467bd',  # Purple
        25: '#8c564b',  # Brown
        30: '#e377c2'   # Pink
    }
    
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
            
            # Trace for Zinssatz (solid line)
            fig.add_trace(go.Scatter(
                x=data['scrape_timestamp'],
                y=data['zinssatz_numeric'],
                mode='lines+markers',
                name=f'{fixierung}J fix - {laufzeit}J ZinsS',
                line=dict(color=color, width=2.5, dash='solid'),
                marker=dict(size=8, symbol='circle'),
                legendgroup=f'fixierung_{fixierung}_laufzeit_{laufzeit}',
                hovertemplate=(
                    f'<b>Fixierung: {fixierung} Jahre</b><br>'
                    f'Laufzeit: {laufzeit} Jahre<br>'
                    'Datum: %{x|%d.%m.%Y}<br>'
                    'Zinssatz: %{y:.3f}%<br>'
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
                marker=dict(size=7, symbol='square'),
                legendgroup=f'fixierung_{fixierung}_laufzeit_{laufzeit}',
                hovertemplate=(
                    f'<b>Fixierung: {fixierung} Jahre</b><br>'
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
    
    # Update layout (no updatemenus - we'll use custom HTML controls)
    fig.update_layout(
        title={
            'text': '🏠 Wohnkredite - Durchblicker-Bestpreis',
            'x': 0.5,
            'xanchor': 'center',
            'font': {'size': 20, 'family': 'Segoe UI, Arial'}
        },
        xaxis=dict(
            title=dict(text='Datum', font=dict(size=14, family='Segoe UI, Arial')),
            showgrid=True,
            gridwidth=1,
            gridcolor='rgba(200,200,200,0.3)',
            tickformat='%d.%m.%Y'
        ),
        yaxis=dict(
            title=dict(text='Zinssatz (%)', font=dict(size=14, family='Segoe UI, Arial')),
            showgrid=True,
            gridwidth=1,
            gridcolor='rgba(200,200,200,0.3)'
        ),
        hovermode='closest',
        plot_bgcolor='rgba(250,250,250,0.9)',
        paper_bgcolor='white',
        font=dict(family='Segoe UI, Arial', size=12),
        legend=dict(
            orientation="v",
            yanchor="top",
            y=1,
            xanchor="left",
            x=1.02,
            bgcolor="rgba(255,255,255,0.8)",
            bordercolor="rgba(0,0,0,0.2)",
            borderwidth=1,
            font=dict(size=10)
        ),
        height=600,
        margin=dict(l=80, r=280, t=80, b=80)
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
    
    # Add traces for each offer
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

        # Trace for fixzinssatz (solid line marker)
        fig.add_trace(go.Scatter(
            x=[date],
            y=[offer['fixzinssatz']],
            mode='markers',
            name=f'{anbieter} - Fixzins',
            line=dict(color=color, width=2),
            marker=dict(
                size=14,
                symbol='star',
                color=color,
                line=dict(width=2, color='black')
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

        # Trace for effektivzinssatz (dashed line marker)
        fig.add_trace(go.Scatter(
            x=[date],
            y=[offer['effektivzinssatz']],
            mode='markers',
            name=f'{anbieter} - Eff. Zins',
            line=dict(color=color, width=2, dash='dash'),
            marker=dict(
                size=12,
                symbol='diamond',
                color=color,
                line=dict(width=2, color='black')
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
    
    # Update layout
    fig.update_layout(
        title={
            'text': '💳 Wohnkredite - Konkurrenzangebote',
            'x': 0.5,
            'xanchor': 'center',
            'font': {'size': 20, 'family': 'Segoe UI, Arial'}
        },
        xaxis=dict(
            title=dict(text='Datum', font=dict(size=14, family='Segoe UI, Arial')),
            showgrid=True,
            gridwidth=1,
            gridcolor='rgba(200,200,200,0.3)',
            tickformat='%d.%m.%Y'
        ),
        yaxis=dict(
            title=dict(text='Zinssatz (%)', font=dict(size=14, family='Segoe UI, Arial')),
            showgrid=True,
            gridwidth=1,
            gridcolor='rgba(200,200,200,0.3)'
        ),
        hovermode='closest',
        plot_bgcolor='rgba(250,250,250,0.9)',
        paper_bgcolor='white',
        font=dict(family='Segoe UI, Arial', size=12),
        legend=dict(
            orientation="v",
            yanchor="top",
            y=1,
            xanchor="left",
            x=1.02,
            bgcolor="rgba(255,255,255,0.8)",
            bordercolor="rgba(0,0,0,0.2)",
            borderwidth=1,
            font=dict(size=10)
        ),
        height=600,
        margin=dict(l=80, r=280, t=80, b=80)
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
    """Generate static PNG chart using matplotlib for individual offers email embedding - Default: Eff. Zinssatz only"""
    
    # Create figure
    plt.figure(figsize=(14, 7))
    
    # Group offers by bank
    offers_by_bank = {}
    for offer in user_offers:
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
                edgecolors='black',
                linewidths=1.5
            )
    
    # Customize plot
    plt.title('Wohnkredite - Konkurrenzangebote (Eff. Zinssatz)', 
              fontsize=16, fontweight='bold', pad=15)
    plt.xlabel('Datum', fontsize=12, fontweight='bold')
    plt.ylabel('Zinssatz (%)', fontsize=12, fontweight='bold')
    
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
    """Generate static PNG chart using matplotlib for email embedding - Default: 25J and Eff. Zinssatz only"""
    
    # Create figure
    plt.figure(figsize=(14, 7))
    
    # Default: Only show 25J Laufzeit and Effektiver Zinssatz
    target_laufzeit = 25
    show_zinssatz = False  # Only show Effektiver Zinssatz
    
    # Plot data for each Fixierung (only for 25J Laufzeit)
    for fixierung in fixierung_values:
        # Filter data for this combination (only 25J Laufzeit)
        mask = (df['fixierung_jahre'] == fixierung) & (df['run_laufzeit_jahre'] == target_laufzeit)
        data = df[mask].copy()
        
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
    
    # Customize plot
    plt.title('Immobilienkredit Zinsentwicklung - 25 Jahre Laufzeit (Eff. Zinssatz)', 
              fontsize=16, fontweight='bold', pad=15)
    plt.xlabel('Datum', fontsize=12, fontweight='bold')
    plt.ylabel('Zinssatz (%)', fontsize=12, fontweight='bold')
    
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
            # Default to last 12 months
            end_date = datetime.now().replace(day=1)
            start_date = datetime(end_date.year - 1, end_date.month, 1)
            print(f"[INFO] View not found, using default date range: {start_date.strftime('%Y-%m')} to {end_date.strftime('%Y-%m')}")
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
        
        if min_date_str and max_date_str:
            # Parse dates (assuming ISO format or similar)
            try:
                min_date = datetime.fromisoformat(min_date_str.replace('Z', '+00:00'))
                max_date = datetime.fromisoformat(max_date_str.replace('Z', '+00:00'))
                
                # Ensure we have at least 12 months of data
                # If the range is shorter, extend backwards
                if (max_date - min_date).days < 365:
                    start_date = datetime(max_date.year - 1, max_date.month, 1)
                    end_date = max_date.replace(day=1)
                else:
                    start_date = min_date.replace(day=1)
                    end_date = max_date.replace(day=1)
                
                print(f"[INFO] Date range from DB: {start_date.strftime('%Y-%m')} to {end_date.strftime('%Y-%m')}")
                return start_date, end_date
            except (ValueError, AttributeError) as e:
                print(f"[WARN] Could not parse dates from DB: {e}")
        
        # Fallback to default
        end_date = datetime.now().replace(day=1)
        start_date = datetime(end_date.year - 1, end_date.month, 1)
        print(f"[INFO] Using default date range: {start_date.strftime('%Y-%m')} to {end_date.strftime('%Y-%m')}")
        return start_date, end_date
        
    except Exception as e:
        print(f"[WARN] Error extracting date range from DB: {e}")
        # Fallback to default
        end_date = datetime.now().replace(day=1)
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
        for month_data in rate_data:
            year = month_data['year']
            month = month_data['month']
            dt = datetime(year, month, 1)
            dates.append(dt)
            
            rates = month_data.get('rates', {})
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
        
        # Add traces for each maturity
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
                    )
                ))
        
        # Update layout
        fig.update_layout(
            title={
                'text': 'EUR SWAP Rates',
                'x': 0.5,
                'xanchor': 'center',
                'font': {'size': 20, 'family': 'Segoe UI, Arial'}
            },
            xaxis=dict(
                title=dict(text='Datum', font=dict(size=14, family='Segoe UI, Arial')),
                showgrid=True,
                gridwidth=1,
                gridcolor='rgba(200,200,200,0.3)',
                tickformat='%d.%m.%Y'
            ),
            yaxis=dict(
                title=dict(text='Zinssatz (%)', font=dict(size=14, family='Segoe UI, Arial')),
                showgrid=True,
                gridwidth=1,
                gridcolor='rgba(200,200,200,0.3)'
            ),
            hovermode='closest',
            plot_bgcolor='rgba(250,250,250,0.9)',
            paper_bgcolor='white',
            font=dict(family='Segoe UI, Arial', size=12),
            legend=dict(
                orientation="v",
                yanchor="top",
                y=1,
                xanchor="left",
                x=1.02,
                bgcolor="rgba(255,255,255,0.8)",
                bordercolor="rgba(0,0,0,0.2)",
                borderwidth=1,
                font=dict(size=10)
            ),
            height=500,
            margin=dict(l=80, r=200, t=80, b=80)
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
        
        return chart_html, png_base64
        
    except ImportError as e:
        print(f"[WARN] swap_data_fetcher not available: {e}")
        return None, None
    except Exception as e:
        print(f"[WARN] Error generating SWAP rates chart: {e}")
        return None, None


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
        
        for month_data in rate_data:
            year = month_data['year']
            month = month_data['month']
            dt = datetime(year, month, 1)
            dates.append(dt)
            
            rates = month_data.get('rates', {})
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
            line=dict(color='#1f77b4', width=2.5),
            marker=dict(size=6, symbol='circle'),
            hovertemplate=(
                '<b>Euribor 3M</b><br>'
                'Datum: %{x|%d.%m.%Y}<br>'
                'Zinssatz: %{y:.2f}%<br>'
                '<extra></extra>'
            )
        ))
        
        # Update layout
        fig.update_layout(
            title={
                'text': 'Euribor 3M',
                'x': 0.5,
                'xanchor': 'center',
                'font': {'size': 20, 'family': 'Segoe UI, Arial'}
            },
            xaxis=dict(
                title=dict(text='Datum', font=dict(size=14, family='Segoe UI, Arial')),
                showgrid=True,
                gridwidth=1,
                gridcolor='rgba(200,200,200,0.3)',
                tickformat='%d.%m.%Y'
            ),
            yaxis=dict(
                title=dict(text='Zinssatz (%)', font=dict(size=14, family='Segoe UI, Arial')),
                showgrid=True,
                gridwidth=1,
                gridcolor='rgba(200,200,200,0.3)'
            ),
            hovermode='closest',
            plot_bgcolor='rgba(250,250,250,0.9)',
            paper_bgcolor='white',
            font=dict(family='Segoe UI, Arial', size=12),
            legend=dict(
                orientation="v",
                yanchor="top",
                y=1,
                xanchor="left",
                x=1.02,
                bgcolor="rgba(255,255,255,0.8)",
                bordercolor="rgba(0,0,0,0.2)",
                borderwidth=1,
                font=dict(size=10)
            ),
            height=500,
            margin=dict(l=80, r=200, t=80, b=80)
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
    """Generate static PNG chart for SWAP rates using matplotlib"""
    dates = []
    swap_data_by_maturity = {
        '5Y': [],
        '10Y': [],
        '15Y': [],
        '20Y': [],
        '25Y': []
    }
    
    for month_data in rate_data:
        year = month_data['year']
        month = month_data['month']
        dt = datetime(year, month, 1)
        dates.append(dt)
        
        rates = month_data.get('rates', {})
        for maturity in swap_data_by_maturity.keys():
            if maturity in rates:
                swap_data_by_maturity[maturity].append(rates[maturity])
            else:
                swap_data_by_maturity[maturity].append(None)
    
    fig, ax = plt.subplots(figsize=(14, 8))
    
    colors = {
        '5Y': '#1f77b4',
        '10Y': '#2ca02c',
        '15Y': '#ff7f0e',
        '20Y': '#d62728',
        '25Y': '#9467bd'
    }
    
    for maturity in ['5Y', '10Y', '15Y', '20Y', '25Y']:
        values = swap_data_by_maturity[maturity]
        if any(v is not None for v in values):
            ax.plot(dates, values, label=f'{maturity} SWAP', color=colors[maturity], 
                   linewidth=2.5, marker='o', markersize=4)
    
    ax.set_xlabel('Datum', fontsize=12, fontfamily='Arial')
    ax.set_ylabel('Zinssatz (%)', fontsize=12, fontfamily='Arial')
    ax.set_title('EUR SWAP Rates', fontsize=16, fontweight='bold', fontfamily='Arial', pad=20)
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


def generate_static_png_euribor(rate_data):
    """Generate static PNG chart for Euribor 3M using matplotlib"""
    dates = []
    euribor_values = []
    
    for month_data in rate_data:
        year = month_data['year']
        month = month_data['month']
        dt = datetime(year, month, 1)
        dates.append(dt)
        
        rates = month_data.get('rates', {})
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


def generate_swap_euribor_section_html(swap_chart_html, euribor_chart_html, swap_png_base64, euribor_png_base64, for_email=False):
    """Generate HTML section for SWAP/Euribor charts
    
    Args:
        swap_chart_html: Plotly HTML for SWAP rates chart (None if unavailable)
        euribor_chart_html: Plotly HTML for Euribor chart (None if unavailable)
        swap_png_base64: Base64 PNG for SWAP rates (for email)
        euribor_png_base64: Base64 PNG for Euribor (for email)
        for_email: if True, use base64 PNG; if False, use Plotly HTML
    """
    if not swap_chart_html and not euribor_chart_html:
        return ""
    
    section_html = '''
        <div class="swap-euribor-section" style="margin-top: 50px; padding: 25px; background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%); border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.1);">
            <h2 style="color: #2c3e50; margin-bottom: 25px; font-size: 1.8em; text-align: center;">📈 Marktzinsen (SWAP & Euribor)</h2>
'''
    
    if for_email:
        # Use static PNG images for email
        if swap_png_base64:
            section_html += f'''
            <div style="margin-bottom: 30px;">
                <h3 style="color: #1b5e20; margin-bottom: 15px;">EUR SWAP Rates</h3>
                <img src="{swap_png_base64}" alt="EUR SWAP Rates" style="width: 100%; max-width: 1400px; height: auto; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);" />
            </div>
'''
        if euribor_png_base64:
            section_html += f'''
            <div style="margin-bottom: 30px;">
                <h3 style="color: #1b5e20; margin-bottom: 15px;">Euribor 3M</h3>
                <img src="{euribor_png_base64}" alt="Euribor 3M" style="width: 100%; max-width: 1400px; height: auto; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);" />
            </div>
'''
    else:
        # Use interactive Plotly charts for web
        if swap_chart_html:
            section_html += f'''
            <div style="margin-bottom: 30px;">
                <h3 style="color: #1b5e20; margin-bottom: 15px;">EUR SWAP Rates</h3>
                {swap_chart_html}
            </div>
'''
        if euribor_chart_html:
            section_html += f'''
            <div style="margin-bottom: 30px;">
                <h3 style="color: #1b5e20; margin-bottom: 15px;">Euribor 3M</h3>
                {euribor_chart_html}
            </div>
'''
    
    section_html += '''
        </div>
'''
    return section_html


def generate_oenb_section_html(screenshots, for_email=False):
    """Generate HTML section for OeNB charts
    
    Args:
        screenshots: dict mapping chart_id to screenshot path
        for_email: if True, use base64 encoding; if False, use relative paths
    """
    if not screenshots:
        return ""
    
    oenb_html = '''
        <div class="oenb-section" style="margin-top: 50px; padding: 25px; background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%); border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.1);">
            <h2 style="color: #2c3e50; margin-bottom: 25px; font-size: 1.8em; text-align: center;">📊 OeNB Wohnimmobilien Dashboard</h2>
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
        
        oenb_html += f'''
            <div style="margin-bottom: 30px;">
                <h3>{chart_name}</h3>
                <img src="{img_src}" alt="{chart_name}" style="width: 100%; max-width: 1400px; height: auto; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);" />
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
    
    # Generate individual offers chart
    individual_chart_result = generate_individual_offers_chart()
    if individual_chart_result[0]:
        individual_chart_html, individual_laufzeit_values, individual_fixierung_values, individual_trace_metadata, individual_png_base64 = individual_chart_result
    else:
        individual_chart_html = None
        individual_laufzeit_values = []
        individual_fixierung_values = []
        individual_trace_metadata = []
        individual_png_base64 = None
    
    # Get all runs data
    runs, all_variations = get_all_runs_data()
    
    # Get latest OeNB screenshots
    oenb_screenshots = get_latest_oenb_screenshots()
    
    # Generate SWAP/Euribor charts
    print("[INFO] Generating SWAP/Euribor charts...")
    swap_chart_result = generate_swap_rates_chart()
    euribor_chart_result = generate_euribor_chart()
    
    if swap_chart_result[0]:
        swap_chart_html, swap_png_base64 = swap_chart_result
    else:
        swap_chart_html, swap_png_base64 = None, None
    
    if euribor_chart_result[0]:
        euribor_chart_html, euribor_png_base64 = euribor_chart_result
    else:
        euribor_chart_html, euribor_png_base64 = None, None
    
    if not runs:
        print("[WARN] No data found in database")
        return False, None
    
    # Get latest run for initial table display
    latest_run = runs[0]
    latest_variations = all_variations[latest_run['id']]
    
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
    
    # Get the latest run for each Laufzeit
    latest_by_laufzeit = {}
    for laufzeit, runs_list in runs_by_laufzeit.items():
        # Sort by date descending and get the latest
        sorted_runs = sorted(runs_list, key=lambda x: x['run']['scrape_date'], reverse=True)
        latest_by_laufzeit[laufzeit] = sorted_runs[0]
    
    # Prepare table data for JavaScript (must be JSON-serializable)
    table_data_for_js = {}
    for laufzeit, data in latest_by_laufzeit.items():
        table_data_for_js[int(laufzeit)] = {
            'run': data['run'],
            'variations': data['variations']
        }
    
    # Create HTML content
    html_content = f'''<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bank Comparison - Housing Loan Analysis (Interactive)</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 20px;
            background: linear-gradient(to bottom right, #f9fafb, #ffffff, #f3f4f6);
            min-height: 100vh;
        }}
        .container {{
            max-width: 1600px;
            margin: 0 auto;
            background-color: white;
            padding: 30px;
            border-radius: 12px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.2);
        }}
        h1 {{
            color: #2c3e50;
            text-align: center;
            margin-bottom: 10px;
            font-size: 2.2em;
        }}
        .subtitle {{
            text-align: center;
            color: #7f8c8d;
            margin-bottom: 30px;
            font-size: 1.1em;
        }}
        .info-badge {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 10px 20px;
            border-radius: 20px;
            display: inline-block;
            margin: 5px;
            font-size: 0.9em;
        }}
        .chart-container {{
            margin-bottom: 40px;
            padding: 25px;
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            border-radius: 12px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        }}
        .chart-controls {{
            display: flex;
            gap: 20px;
            margin-bottom: 20px;
            padding: 15px;
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            flex-wrap: wrap;
            align-items: center;
        }}
        .control-group {{
            display: flex;
            align-items: center;
            gap: 8px;
            flex-wrap: wrap;
        }}
        .control-label {{
            font-weight: bold;
            color: #2c3e50;
            font-size: 14px;
            white-space: nowrap;
        }}
        select, button {{
            padding: 10px 12px;
            border: 2px solid #667eea;
            border-radius: 6px;
            font-size: 14px;
            font-family: 'Segoe UI', Arial;
            cursor: pointer;
            transition: all 0.3s;
            min-height: 40px;
        }}
        select {{
            background: white;
            color: #2c3e50;
            min-width: 140px;
        }}
        select:hover {{
            border-color: #764ba2;
        }}
        button {{
            background: white;
            color: #667eea;
            min-width: 100px;
        }}
        button.active {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }}
        button:hover {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }}
        .run-info {{
            background-color: #ecf0f1;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 30px;
            border-left: 5px solid #3498db;
        }}
        .run-info h3 {{
            margin-top: 0;
            margin-bottom: 10px;
            color: #2c3e50;
            font-size: 1.0em;
        }}
        .run-info-text {{
            color: #2c3e50;
            font-size: 0.75em;
            line-height: 1.6;
            margin: 0;
        }}
        .run-info-grid {{
            display: none;
        }}
        .info-item {{
            display: none;
        }}
        .info-label {{
            display: none;
        }}
        .info-value {{
            display: none;
        }}
        .table-container {{
            overflow-x: auto;
            margin-bottom: 30px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 20px;
            font-size: 0.95em;
        }}
        th {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 15px 12px;
            text-align: left;
            font-weight: 600;
            position: sticky;
            top: 0;
        }}
        td {{
            padding: 12px;
            border-bottom: 1px solid #ecf0f1;
        }}
        tr:hover {{
            background-color: #f8f9fa;
        }}
        tr:nth-child(even) {{
            background-color: #fafbfc;
        }}
        .fixierung-cell {{
            font-weight: bold;
            color: #2c3e50;
            background-color: #e8f4f8 !important;
        }}
        .rate-cell {{
            font-weight: bold;
            color: #27ae60;
            font-size: 1.1em;
        }}
        .timestamp {{
            text-align: center;
            color: #7f8c8d;
            font-size: 0.9em;
            margin-top: 30px;
            padding-top: 20px;
            border-top: 2px solid #ecf0f1;
        }}
        .highlight {{
            background-color: #fff3cd !important;
        }}
        @media (max-width: 768px) {{
            body {{
                margin: 0;
                padding: 5px;
            }}
            .container {{
                margin: 0;
                padding: 10px;
                border-radius: 0;
                box-shadow: none;
            }}
            h1 {{
                font-size: 1.4em;
                margin-bottom: 15px;
            }}
            .subtitle {{
                font-size: 0.9em;
                margin-bottom: 20px;
            }}
            .info-badge {{
                font-size: 0.8em;
                padding: 6px 12px;
                margin: 3px;
            }}
            .run-info {{
                padding: 15px;
                margin-bottom: 20px;
            }}
            .run-info h3 {{
                font-size: 0.9em;
            }}
            .run-info-text {{
                font-size: 0.7em;
            }}
            .run-info-grid {{
                display: none;
            }}
            .info-item {{
                display: none;
            }}
            .chart-container {{
                padding: 15px;
                margin-bottom: 20px;
            }}
            .chart-controls {{
                flex-direction: column;
                gap: 15px;
                padding: 12px;
            }}
            .control-group {{
                width: 100%;
                justify-content: space-between;
                gap: 10px;
            }}
            .control-label {{
                font-size: 13px;
            }}
            select, button {{
                padding: 8px 10px;
                font-size: 13px;
                min-height: 36px;
                flex: 1;
            }}
            select {{
                min-width: auto;
            }}
            button {{
                min-width: auto;
            }}
            /* Plotly chart mobile adjustments */
            #plotly-chart {{
                height: 400px !important;
            }}
            .js-plotly-plot .plotly .modebar {{
                display: none !important;
            }}
            .js-plotly-plot .plotly .legend {{
                display: none !important;
            }}
            table {{
                font-size: 11px;
                min-width: 500px;
            }}
            th, td {{
                padding: 8px 4px;
                white-space: nowrap;
            }}
            .fixierung-cell {{
                font-size: 12px;
            }}
            .rate-cell {{
                font-size: 12px;
            }}
            .table-container {{
                margin-bottom: 20px;
            }}
            .timestamp {{
                font-size: 0.8em;
                margin-top: 20px;
                padding-top: 15px;
            }}
        }}
        @media (max-width: 480px) {{
            body {{
                padding: 2px;
            }}
            .container {{
                padding: 5px;
            }}
            h1 {{
                font-size: 1.2em;
            }}
            .chart-container {{
                padding: 10px;
            }}
            .chart-controls {{
                padding: 8px;
            }}
            .control-group {{
                flex-direction: column;
                align-items: stretch;
                gap: 8px;
            }}
            .control-label {{
                text-align: center;
            }}
            select, button {{
                width: 100%;
                margin: 2px 0;
            }}
            #plotly-chart {{
                height: 300px !important;
            }}
            table {{
                font-size: 10px;
                min-width: 450px;
            }}
            th, td {{
                padding: 6px 2px;
            }}
        }}
        .nav-tabs {{
            display: flex;
            gap: 0;
            margin-bottom: 30px;
            border-bottom: 2px solid #ecf0f1;
            background-color: #f8f9fa;
            border-radius: 8px 8px 0 0;
            overflow: hidden;
        }}
        .nav-tab {{
            flex: 1;
            padding: 15px 20px;
            text-align: center;
            background-color: #e8ecef;
            color: #495057;
            text-decoration: none;
            font-weight: 600;
            font-size: 1.1em;
            transition: all 0.3s ease;
            border: none;
            cursor: pointer;
            border-bottom: 3px solid transparent;
        }}
        .nav-tab:hover {{
            background-color: #dee2e6;
            color: #212529;
            text-decoration: none;
        }}
        .nav-tab.active {{
            background-color: white;
            color: #667eea;
            border-bottom: 3px solid #667eea;
        }}
        .nav-tab:first-child {{
            border-right: 1px solid #dee2e6;
        }}
        @media (max-width: 768px) {{
            .nav-tabs {{
                margin-bottom: 20px;
            }}
            .nav-tab {{
                padding: 12px 10px;
                font-size: 0.95em;
            }}
        }}
        @media (max-width: 480px) {{
            .nav-tab {{
                padding: 10px 8px;
                font-size: 0.85em;
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
        
        <div class="chart-container">
            <div class="chart-controls">
                <div class="control-group">
                    <span class="control-label">Laufzeit:</span>
                    <select id="laufzeit-filter">
                        <option value="all">Alle Laufzeiten</option>
{f''.join([f'                        <option value="{lz}"{" selected" if lz == 25 else ""}>{lz} Jahre</option>\n' for lz in laufzeit_values])}                    </select>
                </div>
                <div class="control-group">
                    <span class="control-label">Fixierung:</span>
                    <select id="fixierung-filter">
                        <option value="all">Alle Fixierungen</option>
{f''.join([f'                        <option value="{fx}">{fx} Jahre</option>\n' for fx in fixierung_values])}                    </select>
                </div>
                <div class="control-group">
                    <span class="control-label">Anzeigen:</span>
                    <button id="btn-beide" onclick="setZinssatzFilter('beide')">Beide</button>
                    <button id="btn-zinssatz" onclick="setZinssatzFilter('zinssatz')">Nur Zinssatz</button>
                    <button id="btn-effektiver" class="active" onclick="setZinssatzFilter('effektiver')">Nur Eff. Zinssatz</button>
                </div>
            </div>
            
            {chart_html}
            
            <script>
                // Store trace metadata
                const traceMetadata = {json.dumps(trace_metadata)};
                
                // Store table data for each Laufzeit
                const tableData = {json.dumps(table_data_for_js)};
                
                // Current filter states
                let currentLaufzeit = '25';
                let currentFixierung = 'all';
                let currentZinssatz = 'effektiver';
                
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
                        renderTables(tableData[latestLaufzeit], latestLaufzeit, 'Aktuellste Berechnung (Alle Laufzeiten)');
                    }} else {{
                        // Show latest run for selected Laufzeit
                        const laufzeit = parseInt(currentLaufzeit);
                        if (tableData[laufzeit]) {{
                            renderTables(tableData[laufzeit], laufzeit, `Aktuelle Konditionen für ${{laufzeit}} Jahre Laufzeit`);
                        }}
                    }}
                }}
                
                // Render tables with given data
                function renderTables(data, laufzeit, headerText) {{
                    const run = data.run;
                    const variations = data.variations;
                    
                    // Update run info section
                    document.querySelector('.run-info h3').textContent = '📊 Parameter für ' + laufzeit + ' Jahre Laufzeit';
                    
                    // Update Finanzierungsdetails table title
                    const finanzTitle = document.querySelector('.table-container h2');
                    if (finanzTitle) {{
                        finanzTitle.textContent = '📋 Finanzierungsdetails - Aktuelle Konditionen für ' + laufzeit + ' Jahre Laufzeit';
                    }}
                    
                    // Update run info text paragraph
                    const runInfoText = document.getElementById('run-info-text');
                    if (runInfoText) {{
                        runInfoText.textContent = 
                            'Kreditbetrag: €' + run.kreditbetrag.toLocaleString('de-DE') + 
                            ', Laufzeit: ' + run.laufzeit_jahre + ' Jahre' +
                            ', Kaufpreis: €' + run.kaufpreis.toLocaleString('de-DE') +
                            ', Kaufnebenkosten: €' + run.kaufnebenkosten.toLocaleString('de-DE') +
                            ', Eigenmittel: €' + run.eigenmittel.toLocaleString('de-DE') +
                            ', Haushalt Alter: ' + run.haushalt_alter + ' Jahre' +
                            ', Netto-Einkommen: €' + run.haushalt_einkommen.toFixed(2) + '/Monat' +
                            ', Wohnnutzfläche: ' + run.haushalt_nutzflaeche + ' m²';
                    }}
                    
                    // Build Finanzierungsdetails table
                    let finanzTable = '';
                    variations.forEach(v => {{
                        if (v.rate) {{
                            const anschluss = v.anschlusskondition ? 
                                `<br><small style='color: #7f8c8d;'>Anschluss: ${{v.anschlusskondition}}</small>` : '';
                            finanzTable += `
                                <tr>
                                    <td class="fixierung-cell">${{v.fixierung_jahre}}J</td>
                                    <td class="rate-cell">€${{v.rate.toLocaleString('de-DE', {{minimumFractionDigits: 2, maximumFractionDigits: 2}})}}</td>
                                    <td>${{v.zinssatz}}${{anschluss}}</td>
                                    <td>${{v.effektiver_zinssatz}}</td>
                                    <td>${{v.laufzeit}}</td>
                                    <td>€${{v.kreditbetrag.toLocaleString('de-DE', {{minimumFractionDigits: 2, maximumFractionDigits: 2}})}}</td>
                                    <td>€${{v.gesamtbetrag.toLocaleString('de-DE', {{minimumFractionDigits: 2, maximumFractionDigits: 2}})}}</td>
                                    <td>€${{v.einberechnete_kosten.toLocaleString('de-DE', {{minimumFractionDigits: 2, maximumFractionDigits: 2}})}}</td>
                                </tr>`;
                        }} else {{
                            finanzTable += `
                                <tr>
                                    <td class="fixierung-cell">${{v.fixierung_jahre}}J</td>
                                    <td colspan="7" style="text-align: center; color: #95a5a6;">Keine Daten verfügbar</td>
                                </tr>`;
                        }}
                    }});
                    document.querySelector('#finanz-tbody').innerHTML = finanzTable;
                    
                    
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
        
{f'''
        <div class="chart-container" style="margin-top: 50px;">
            <div class="chart-controls">
                <div class="control-group">
                    <span class="control-label">Laufzeit:</span>
                    <select id="individual-laufzeit-filter">
                        <option value="all">Alle Laufzeiten</option>
{f''.join([f'                        <option value="{lz}">{lz} Jahre</option>\n' for lz in individual_laufzeit_values])}                    </select>
                </div>
                <div class="control-group">
                    <span class="control-label">Fixierung:</span>
                    <select id="individual-fixierung-filter">
                        <option value="all">Alle Fixierungen</option>
{f''.join([f'                        <option value="{fx}">{fx} Jahre</option>\n' for fx in individual_fixierung_values])}                    </select>
                </div>
                <div class="control-group">
                    <span class="control-label">Anzeigen:</span>
                    <button id="individual-btn-beide" onclick="setIndividualZinssatzFilter('beide')">Beide</button>
                    <button id="individual-btn-zinssatz" onclick="setIndividualZinssatzFilter('zinssatz')">Nur Zinssatz</button>
                    <button id="individual-btn-effektiver" class="active" onclick="setIndividualZinssatzFilter('effektiver')">Nur Eff. Zinssatz</button>
                </div>
            </div>
            
            {individual_chart_html if individual_chart_html else '<p style="text-align: center; color: #7f8c8d; padding: 40px;">Keine Konkurrenzangebote verfügbar</p>'}
            
            <script>
                // Store trace metadata for individual offers chart
                const individualTraceMetadata = {json.dumps(individual_trace_metadata) if individual_chart_html else '[]'};
                
                // Current filter states for individual offers chart
                let individualCurrentLaufzeit = 'all';
                let individualCurrentFixierung = 'all';
                let individualCurrentZinssatz = 'effektiver';
                
                // Apply filters for individual offers chart
                function applyIndividualFilters() {{
                    if (!document.getElementById('plotly-individual-offers-chart')) {{
                        return;
                    }}
                    
                    const data = document.getElementById('plotly-individual-offers-chart').data;
                    
                    const visible = [];
                    
                    for (let i = 0; i < individualTraceMetadata.length && i < data.length; i++) {{
                        const meta = individualTraceMetadata[i];
                        
                        // Check Laufzeit filter
                        const laufzeitMatch = individualCurrentLaufzeit === 'all' || 
                            (meta.laufzeit !== null && meta.laufzeit === parseInt(individualCurrentLaufzeit));
                        
                        // Check Fixierung filter
                        const fixierungMatch = individualCurrentFixierung === 'all' || 
                            (meta.fixierung !== null && meta.fixierung === parseFloat(individualCurrentFixierung));
                        
                        // Check Zinssatz type filter
                        let zinssatzMatch = true;
                        if (individualCurrentZinssatz === 'zinssatz') {{
                            zinssatzMatch = meta.type === 'user_offer_fix';
                        }} else if (individualCurrentZinssatz === 'effektiver') {{
                            zinssatzMatch = meta.type === 'user_offer_eff';
                        }}
                        // 'beide' means both are shown, so zinssatzMatch stays true
                        
                        // Return true only if ALL conditions match (AND logic)
                        visible.push(laufzeitMatch && fixierungMatch && zinssatzMatch);
                    }}
                    
                    // Update the Plotly chart
                    Plotly.restyle('plotly-individual-offers-chart', {{'visible': visible}});
                }}
                
                // Mobile responsiveness for individual offers Plotly chart (same approach as Durchblicker chart)
                function handleIndividualChartResize() {{
                    const chartDiv = document.getElementById('plotly-individual-offers-chart');
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
                        
                        Plotly.relayout('plotly-individual-offers-chart', {{
                            height: newHeight,
                            margin: newMargin,
                            showlegend: showLegend
                        }});
                    }}
                }}
                
                // Call on load and resize
                window.addEventListener('load', handleIndividualChartResize);
                window.addEventListener('resize', handleIndividualChartResize);
                
                // Laufzeit dropdown change handler for individual offers
                const individualLaufzeitFilter = document.getElementById('individual-laufzeit-filter');
                if (individualLaufzeitFilter) {{
                    individualLaufzeitFilter.addEventListener('change', function(e) {{
                        individualCurrentLaufzeit = e.target.value;
                        applyIndividualFilters();
                    }});
                }}
                
                // Fixierung dropdown change handler for individual offers
                const individualFixierungFilter = document.getElementById('individual-fixierung-filter');
                if (individualFixierungFilter) {{
                    individualFixierungFilter.addEventListener('change', function(e) {{
                        individualCurrentFixierung = e.target.value;
                        applyIndividualFilters();
                    }});
                }}
                
                // Zinssatz button click handler for individual offers
                function setIndividualZinssatzFilter(type) {{
                    individualCurrentZinssatz = type;
                    
                    // Update button styling
                    document.getElementById('individual-btn-beide').classList.remove('active');
                    document.getElementById('individual-btn-zinssatz').classList.remove('active');
                    document.getElementById('individual-btn-effektiver').classList.remove('active');
                    document.getElementById('individual-btn-' + type).classList.add('active');
                    
                    applyIndividualFilters();
                }}
                
                // Apply initial filters after chart loads
                setTimeout(() => {{
                    applyIndividualFilters();
                }}, 1500);
            </script>
        </div>
''' if individual_chart_html else ''}
        
        <div class="table-container">
            <h2 style="color: #2c3e50; margin-bottom: 20px;">📋 Finanzierungsdetails - Aktuelle Konditionen für 25 Jahre Laufzeit</h2>
            <table>
                <thead>
                    <tr>
                        <th>Fixierung</th>
                        <th>Monatliche Rate</th>
                        <th>Zinssatz</th>
                        <th>Effektiver Zinssatz</th>
                        <th>Laufzeit</th>
                        <th>Kreditbetrag</th>
                        <th>Gesamtbetrag</th>
                        <th>Einberechnete Kosten</th>
                    </tr>
                </thead>
                <tbody id="finanz-tbody">
'''
    
    # Add table rows for latest variations
    for var in latest_variations:
        if var['rate']:
            anschluss_note = f"<br><small style='color: #7f8c8d;'>Anschluss: {var['anschlusskondition']}</small>" if var['anschlusskondition'] else ""
            
            html_content += f'''
                    <tr>
                        <td class="fixierung-cell">{var['fixierung_jahre']}J</td>
                        <td class="rate-cell">€{var['rate']:,.2f}</td>
                        <td>{var['zinssatz']}{anschluss_note}</td>
                        <td>{var['effektiver_zinssatz']}</td>
                        <td>{var['laufzeit']}</td>
                        <td>€{var['kreditbetrag']:,.2f}</td>
                        <td>€{var['gesamtbetrag']:,.2f}</td>
                        <td>{var['besicherung']}</td>
                    </tr>
'''
        else:
            html_content += f'''
                    <tr>
                        <td class="fixierung-cell">{var['fixierung_jahre']}J</td>
                        <td colspan="7" style="text-align: center; color: #95a5a6;">Keine Daten verfügbar</td>
                    </tr>
'''
    
    html_content += f'''
                </tbody>
            </table>
        </div>
        
        <div class="run-info">
            <h3>📊 Parameter für 25 Jahre Laufzeit</h3>
            <p class="run-info-text" id="run-info-text">Kreditbetrag: €{latest_run['kreditbetrag']:,.0f}, Laufzeit: {latest_run['laufzeit_jahre']} Jahre, Kaufpreis: €{latest_run['kaufpreis']:,.0f}, Kaufnebenkosten: €{latest_run['kaufnebenkosten']:,.0f}, Eigenmittel: €{latest_run['eigenmittel']:,.0f}, Haushalt Alter: {latest_run['haushalt_alter']} Jahre, Netto-Einkommen: €{latest_run['haushalt_einkommen']:,.2f}/Monat, Wohnnutzfläche: {latest_run['haushalt_nutzflaeche']} m²</p>
        </div>
        
'''
    
    # Add OeNB section if screenshots are available
    oenb_section_html = generate_oenb_section_html(oenb_screenshots)
    html_content += oenb_section_html
    
    # Add SWAP/Euribor section if charts are available
    swap_euribor_section_html = generate_swap_euribor_section_html(
        swap_chart_html, euribor_chart_html, swap_png_base64, euribor_png_base64, for_email=False
    )
    html_content += swap_euribor_section_html
    
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
    return True, png_base64, individual_png_base64


def generate_email_html(png_base64, individual_png_base64=None):
    """Generate simplified HTML for email with static PNG chart (no JavaScript)"""
    
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
        swap_chart_html, swap_png_base64 = swap_chart_result
    else:
        swap_chart_html, swap_png_base64 = None, None
    
    if euribor_chart_result[0]:
        euribor_chart_html, euribor_png_base64 = euribor_chart_result
    else:
        euribor_chart_html, euribor_png_base64 = None, None
    
    # Get 25J run for table display (default)
    latest_run = None
    latest_variations = None
    
    # Find the latest 25J run
    for run in runs:
        if run['laufzeit_jahre'] == 25:
            latest_run = run
            latest_variations = all_variations[run['id']]
            break
    
    # Fallback to first run if no 25J found
    if not latest_run:
        latest_run = runs[0]
        latest_variations = all_variations[latest_run['id']]
    
    # Create simplified HTML content for email (no JavaScript)
    html_content = f'''<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bank Comparison - Housing Loan Analysis</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 20px;
            background: linear-gradient(to bottom right, #f9fafb, #ffffff, #f3f4f6);
            min-height: 100vh;
        }}
        .interactive-button {{
            display: block;
            width: fit-content;
            margin: 25px auto;
            padding: 15px 30px;
            background-color: #667eea !important;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white !important;
            text-decoration: none !important;
            border-radius: 8px;
            font-size: 1.1em;
            font-weight: bold;
            text-align: center;
            box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
            border: 2px solid #667eea;
            transition: all 0.3s;
        }}
        .interactive-button:hover {{
            background-color: #764ba2 !important;
            background: linear-gradient(135deg, #764ba2 0%, #667eea 100%);
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(102, 126, 234, 0.6);
            text-decoration: none !important;
            color: white !important;
        }}
        .interactive-button:visited {{
            color: white !important;
            text-decoration: none !important;
        }}
        .interactive-button:link {{
            color: white !important;
            text-decoration: none !important;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background-color: white;
            padding: 30px;
            border-radius: 12px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.2);
        }}
        h1 {{
            color: #2c3e50;
            text-align: center;
            margin-bottom: 10px;
            font-size: 2.2em;
        }}
        h2 {{
            color: #2c3e50;
            font-size: 1.3em;
            margin-bottom: 15px;
            font-weight: 600;
        }}
        h3 {{
            color: #2c3e50;
            font-size: 1.1em;
            margin-bottom: 12px;
            font-weight: 600;
        }}
        .subtitle {{
            text-align: center;
            color: #7f8c8d;
            margin-bottom: 30px;
            font-size: 1.1em;
        }}
        .chart-container {{
            margin-bottom: 40px;
            padding: 25px;
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            border-radius: 12px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
            text-align: center;
        }}
        .chart-container img {{
            max-width: 100%;
            height: auto;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        .run-info {{
            background-color: #ecf0f1;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 30px;
            border-left: 5px solid #3498db;
        }}
        .run-info h3 {{
            margin-top: 0;
            margin-bottom: 10px;
            color: #2c3e50;
            font-size: 1.0em;
        }}
        .run-info-text {{
            color: #2c3e50;
            font-size: 0.75em;
            line-height: 1.6;
            margin: 0;
        }}
        .run-info-grid {{
            display: none;
        }}
        .info-item {{
            display: none;
        }}
        .info-label {{
            display: none;
        }}
        .info-value {{
            display: none;
        }}
        .table-container {{
            overflow-x: auto;
            margin-bottom: 30px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 20px;
            font-size: 0.95em;
        }}
        th {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 15px 12px;
            text-align: left;
            font-weight: 600;
        }}
        td {{
            padding: 12px;
            border-bottom: 1px solid #ecf0f1;
        }}
        tr:hover {{
            background-color: #f8f9fa;
        }}
        tr:nth-child(even) {{
            background-color: #fafbfc;
        }}
        .fixierung-cell {{
            font-weight: bold;
            color: #2c3e50;
            background-color: #e8f4f8 !important;
        }}
        .rate-cell {{
            font-weight: bold;
            color: #27ae60;
            font-size: 1.1em;
        }}
        .timestamp {{
            text-align: center;
            color: #7f8c8d;
            font-size: 0.9em;
            margin-top: 30px;
            padding-top: 20px;
            border-top: 2px solid #ecf0f1;
        }}
        .highlight {{
            background-color: #fff3cd !important;
        }}
        @media (max-width: 768px) {{
            body {{
                margin: 0;
                padding: 5px;
            }}
            .container {{
                margin: 0;
                padding: 10px;
                border-radius: 0;
                box-shadow: none;
            }}
            h1 {{
                font-size: 1.4em;
                margin-bottom: 15px;
            }}
            h2 {{
                font-size: 1.0em !important;
                margin-bottom: 10px;
            }}
            h3 {{
                font-size: 0.9em !important;
                margin-bottom: 8px;
            }}
            .subtitle {{
                font-size: 0.9em;
                margin-bottom: 20px;
            }}
            .info-badge {{
                font-size: 0.8em;
                padding: 6px 12px;
                margin: 3px;
            }}
            .run-info {{
                padding: 15px;
                margin-bottom: 20px;
            }}
            .run-info h3 {{
                font-size: 0.9em;
            }}
            .run-info-text {{
                font-size: 0.7em;
            }}
            .run-info-grid {{
                display: none;
            }}
            .info-item {{
                display: none;
            }}
            .chart-container {{
                padding: 15px;
                margin-bottom: 20px;
            }}
            .chart-controls {{
                flex-direction: column;
                gap: 15px;
                padding: 12px;
            }}
            .control-group {{
                width: 100%;
                justify-content: space-between;
                gap: 10px;
            }}
            .control-label {{
                font-size: 13px;
            }}
            select, button {{
                padding: 8px 10px;
                font-size: 13px;
                min-height: 36px;
                flex: 1;
            }}
            select {{
                min-width: auto;
            }}
            button {{
                min-width: auto;
            }}
            /* Plotly chart mobile adjustments */
            #plotly-chart {{
                height: 400px !important;
            }}
            .js-plotly-plot .plotly .modebar {{
                display: none !important;
            }}
            .js-plotly-plot .plotly .legend {{
                display: none !important;
            }}
            /* Hide legend for individual offers chart on mobile */
            #plotly-individual-offers-chart .js-plotly-plot .plotly .legend {{
                display: none !important;
            }}
            /* Expand plot area when legend is hidden - adjust margins */
            #plotly-individual-offers-chart .js-plotly-plot {{
                width: 100% !important;
                margin-right: 0 !important;
            }}
            #plotly-individual-offers-chart .js-plotly-plot .plotly {{
                width: 100% !important;
            }}
            #plotly-individual-offers-chart .js-plotly-plot .plotly .main-svg {{
                width: 100% !important;
            }}
            table {{
                font-size: 11px;
                min-width: 500px;
            }}
            th, td {{
                padding: 8px 4px;
                white-space: nowrap;
            }}
            .fixierung-cell {{
                font-size: 12px;
            }}
            .rate-cell {{
                font-size: 12px;
            }}
            .table-container {{
                margin-bottom: 20px;
            }}
            .timestamp {{
                font-size: 0.8em;
                margin-top: 20px;
                padding-top: 15px;
            }}
        }}
        @media (max-width: 480px) {{
            body {{
                padding: 2px;
            }}
            .container {{
                padding: 5px;
            }}
            h1 {{
                font-size: 1.2em;
            }}
            h2 {{
                font-size: 0.9em !important;
                margin-bottom: 8px;
            }}
            h3 {{
                font-size: 0.85em !important;
                margin-bottom: 6px;
            }}
            .chart-container {{
                padding: 10px;
            }}
            .chart-controls {{
                padding: 8px;
            }}
            .control-group {{
                flex-direction: column;
                align-items: stretch;
                gap: 8px;
            }}
            .control-label {{
                text-align: center;
            }}
            select, button {{
                width: 100%;
                margin: 2px 0;
            }}
            #plotly-chart {{
                height: 300px !important;
            }}
            /* Hide legend for individual offers chart on small mobile */
            #plotly-individual-offers-chart .js-plotly-plot .plotly .legend {{
                display: none !important;
            }}
            /* Expand plot area when legend is hidden - adjust margins */
            #plotly-individual-offers-chart .js-plotly-plot {{
                width: 100% !important;
                margin-right: 0 !important;
            }}
            #plotly-individual-offers-chart .js-plotly-plot .plotly {{
                width: 100% !important;
            }}
            #plotly-individual-offers-chart .js-plotly-plot .plotly .main-svg {{
                width: 100% !important;
            }}
            table {{
                font-size: 10px;
                min-width: 450px;
            }}
            th, td {{
                padding: 6px 2px;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
                <h1>🏠 Housing Loan Comparison</h1>
                <div class="subtitle">
                    Zinsentwicklung - 25 Jahre Laufzeit (Eff. Zinssatz)
                </div>
        
        <a href="https://smartprototypes.net/Bank_market_overview/bank_comparison_housing_loan_durchblicker.html" class="interactive-button" target="_blank" style="background-color: #667eea !important; color: white !important; text-decoration: none !important;">
            🔗 Zu den interaktiven Charts
        </a>
        
        <div class="chart-container">
            <h2>📊 Wohnkredite - Durchblicker-Bestpreis</h2>
            <img src="data:image/png;base64,{png_base64}" alt="Housing Loan Interest Rate Chart">
        </div>
        
{f'''
        <div class="chart-container" style="margin-top: 40px;">
            <h2>💳 Wohnkredite - Konkurrenzangebote</h2>
            <img src="data:image/png;base64,{individual_png_base64}" alt="Individual Loan Offers Chart">
        </div>
''' if individual_png_base64 else ''}
        
        <div class="table-container">
            <h2>📋 Finanzierungsdetails - Aktuelle Konditionen für 25 Jahre Laufzeit</h2>
            <table>
                <thead>
                    <tr>
                        <th>Fixierung</th>
                        <th>Monatliche Rate</th>
                        <th>Zinssatz</th>
                        <th>Effektiver Zinssatz</th>
                        <th>Laufzeit</th>
                        <th>Kreditbetrag</th>
                        <th>Gesamtbetrag</th>
                        <th>Einberechnete Kosten</th>
                    </tr>
                </thead>
                <tbody>
'''
    
    # Add table rows for latest variations
    for var in latest_variations:
        if var['rate']:
            anschluss_note = f"<br><small style='color: #7f8c8d;'>Anschluss: {var['anschlusskondition']}</small>" if var['anschlusskondition'] else ""
            
            html_content += f'''
                    <tr>
                        <td class="fixierung-cell">{var['fixierung_jahre']}J</td>
                        <td class="rate-cell">€{var['rate']:,.2f}</td>
                        <td>{var['zinssatz']}{anschluss_note}</td>
                        <td>{var['effektiver_zinssatz']}</td>
                        <td>{var['laufzeit']}</td>
                        <td>€{var['kreditbetrag']:,.2f}</td>
                        <td>€{var['gesamtbetrag']:,.2f}</td>
                        <td>{var['besicherung']}</td>
                    </tr>
'''
        else:
            html_content += f'''
                    <tr>
                        <td class="fixierung-cell">{var['fixierung_jahre']}J</td>
                        <td colspan="7" style="text-align: center; color: #95a5a6;">Keine Daten verfügbar</td>
                    </tr>
'''
    
    html_content += f'''
                </tbody>
            </table>
        </div>
        
        <div class="run-info">
            <h3>📊 Parameter für 25 Jahre Laufzeit</h3>
            <p class="run-info-text">Kreditbetrag: €{latest_run['kreditbetrag']:,.0f}, Laufzeit: {latest_run['laufzeit_jahre']} Jahre, Kaufpreis: €{latest_run['kaufpreis']:,.0f}, Kaufnebenkosten: €{latest_run['kaufnebenkosten']:,.0f}, Eigenmittel: €{latest_run['eigenmittel']:,.0f}, Haushalt Alter: {latest_run['haushalt_alter']} Jahre, Netto-Einkommen: €{latest_run['haushalt_einkommen']:,.2f}/Monat, Wohnnutzfläche: {latest_run['haushalt_nutzflaeche']} m²</p>
        </div>
        
        <div class="timestamp">
            Last Updated: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}<br>
            Data Source: Housing Loan Database | Latest Run ID: {latest_run['id']}<br>
        </div>
'''
    
    # Add OeNB section if screenshots are available (for email, use base64)
    oenb_section_html = generate_oenb_section_html(oenb_screenshots, for_email=True)
    html_content += oenb_section_html
    
    # Add SWAP/Euribor section if charts are available (for email, use base64 PNG)
    swap_euribor_section_html = generate_swap_euribor_section_html(
        swap_chart_html, euribor_chart_html, swap_png_base64, euribor_png_base64, for_email=True
    )
    html_content += swap_euribor_section_html
    
    html_content += '''
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
    success, png_base64, individual_png_base64 = generate_html()
    
    if success:
        print("\n[SUCCESS] Interactive HTML report generated successfully!")
        print(f"   [FILE] Web HTML: {HTML_PATH}")
        print(f"   [FILE] Chart PNG: {CHART_PNG_PATH}")
        if individual_png_base64:
            print(f"   [FILE] Individual Offers Chart PNG: {INDIVIDUAL_OFFERS_CHART_PNG_PATH}")
        
        # Generate email HTML (with static PNGs)
        print("\n[INFO] Generating email-friendly HTML...")
        email_success = generate_email_html(png_base64, individual_png_base64)
        
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
