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
    
    # Add user loan offers if available
    try:
        user_offers = get_all_loan_offers()
        
        if user_offers:
            print(f"[INFO] Adding {len(user_offers)} individual user offers to chart...")
            
            # Get unique anbieters for color assignment
            anbieters = list(set(offer['anbieter'] for offer in user_offers))
            
            # Color palette for different anbieters
            colors_user = {
                # Predefined colors for known banks
                'UniCredit Bank Austria AG': '#FF0000',  # Red
                'Raiffeisen': '#FF6B6B',  # Light red
                'Sparkasse': '#4ECDC4',  # Turquoise
                'Erste Bank': '#95E1D3',  # Light turquoise
            }
            
            # Default colors for other banks
            default_colors = ['#FFA500', '#FFD700', '#FF69B4', '#FF1493', '#32CD32', '#1E90FF']
            
            anbieter_traces = {}  # Track traces per anbieter
            
            for i, offer in enumerate(user_offers):
                anbieter = offer['anbieter']
                date = offer['angebotsdatum']
                laufzeit_numeric = offer.get('laufzeit_numeric')  # Get parsed laufzeit
                fixzins_years = offer.get('fixzinssatz_in_jahren_numeric')
                fixzins_display = offer.get('fixzinssatz_in_jahren_display') or "n/a"
                
                # Get color for this anbieter
                color = colors_user.get(anbieter, default_colors[i % len(default_colors)])
                
                # Create trace name pattern for grouping
                trace_name = f"User Offer: {anbieter[:20]}..."
                
                # Trace for fixzinssatz
                fig.add_trace(go.Scatter(
                    x=[date],
                    y=[offer['fixzinssatz']],
                    mode='markers',
                    name=trace_name,
                    line=dict(color=color, width=1),
                    marker=dict(size=12, symbol='star', color=color, line=dict(width=2, color='black')),
                    legendgroup='user_offers',
                    hovertemplate=(
                        f'<b>Individual Offer - {anbieter}</b><br>'
                        'Datum: %{x|%d.%m.%Y}<br>'
                        f'Fixzins: {offer["fixzinssatz"]:.3f}%<br>'
                        f'Eff. Zins: {offer["effektivzinssatz"]:.3f}%<br>'
                        f'Laufzeit: {offer.get("laufzeit", "N/A")}<br>'
                        f'Fixzinsperiode: {fixzins_display}<br>'
                        '<extra></extra>'
                    ),
                    visible=False,  # Hidden by default
                    customdata=[[laufzeit_numeric, 'user_offer_fix', fixzins_years]]
                ))
                
                # Trace for effektivzinssatz
                fig.add_trace(go.Scatter(
                    x=[date],
                    y=[offer['effektivzinssatz']],
                    mode='markers',
                    name=trace_name + ' (Eff.)',
                    line=dict(color=color, width=1),
                    marker=dict(size=12, symbol='diamond', color=color, line=dict(width=2, color='black')),
                    legendgroup='user_offers',
                    hovertemplate=(
                        f'<b>Individual Offer - {anbieter}</b><br>'
                        'Datum: %{x|%d.%m.%Y}<br>'
                        f'Fixzins: {offer["fixzinssatz"]:.3f}%<br>'
                        f'Eff. Zins: {offer["effektivzinssatz"]:.3f}%<br>'
                        f'Laufzeit: {offer.get("laufzeit", "N/A")}<br>'
                        f'Fixzinsperiode: {fixzins_display}<br>'
                        '<extra></extra>'
                    ),
                    visible=False,  # Hidden by default
                    customdata=[[laufzeit_numeric, 'user_offer_eff', fixzins_years]]
                ))
                
    except Exception as e:
        print(f"[WARN] Could not add user offers to chart: {e}")
    
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
            'text': '🏠 Immobilienkredit Zinsentwicklung - Interaktive Analyse',
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
    
    return chart_html, laufzeit_values, trace_metadata, png_base64


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


def generate_html():
    """Generate HTML page with interactive Plotly chart and data tables"""
    
    # Generate chart
    chart_html, laufzeit_values, trace_metadata, png_base64 = generate_interactive_chart()
    
    if not chart_html:
        print("[WARN] No data found in database")
        return False, None
    
    # Get all runs data
    runs, all_variations = get_all_runs_data()
    
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
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 30px;
            border-left: 5px solid #3498db;
        }}
        .run-info h3 {{
            margin-top: 0;
            color: #2c3e50;
            font-size: 1.3em;
        }}
        .run-info-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 15px;
            margin-top: 15px;
        }}
        .info-item {{
            display: flex;
            justify-content: space-between;
            padding: 8px;
            background-color: white;
            border-radius: 4px;
        }}
        .info-label {{
            font-weight: bold;
            color: #34495e;
        }}
        .info-value {{
            color: #2c3e50;
            font-family: monospace;
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
                font-size: 1.1em;
            }}
            .run-info-grid {{
                grid-template-columns: 1fr;
                gap: 10px;
            }}
            .info-item {{
                padding: 6px;
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
                    <span class="control-label">Anzeigen:</span>
                    <button id="btn-beide" onclick="setZinssatzFilter('beide')">Beide</button>
                    <button id="btn-zinssatz" onclick="setZinssatzFilter('zinssatz')">Nur Zinssatz</button>
                    <button id="btn-effektiver" class="active" onclick="setZinssatzFilter('effektiver')">Nur Eff. Zinssatz</button>
                </div>
                <div class="control-group">
                    <input type="checkbox" id="show-user-offers" onchange="toggleUserOffers()" />
                    <label for="show-user-offers" style="font-weight: bold; cursor: pointer;">Show Individual Offers</label>
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
                let currentZinssatz = 'effektiver';
                
                // Apply combined filters (chart + tables)
                function applyFilters() {{
                    const data = document.getElementById('plotly-chart').data;
                    
                    // Update chart visibility
                    const visible = [];
                    
                    for (let i = 0; i < traceMetadata.length && i < data.length; i++) {{
                        const meta = traceMetadata[i];
                        const customdata = data[i].customdata;
                        
                        // Check if this is a user offer
                        const isUserOffer = customdata && customdata.length > 0 && 
                                          (customdata[0][1] === 'user_offer_fix' || customdata[0][1] === 'user_offer_eff');
                        
                        if (isUserOffer) {{
                            // Handle user offers filtering
                            // Check if checkbox is checked
                            const checkbox = document.getElementById('show-user-offers');
                            const showUserOffers = checkbox && checkbox.checked;
                            
                            if (!showUserOffers) {{
                                visible.push(false);
                                continue;
                            }}
                            
                            // Get laufzeit from customdata (first element)
                            const userLaufzeit = customdata[0][0];
                            
                            // Check Laufzeit filter for user offers
                            const laufzeitMatch = currentLaufzeit === 'all' || userLaufzeit === parseInt(currentLaufzeit);
                            
                            // Check Zinssatz type filter for user offers
                            let zinssatzMatch = true;
                            if (currentZinssatz === 'zinssatz') {{
                                zinssatzMatch = customdata[0][1] === 'user_offer_fix';
                            }} else if (currentZinssatz === 'effektiver') {{
                                zinssatzMatch = customdata[0][1] === 'user_offer_eff';
                            }}
                            // 'beide' means both are shown, so zinssatzMatch stays true
                            
                            // Return true only if BOTH conditions match (AND logic)
                            visible.push(laufzeitMatch && zinssatzMatch);
                        }} else {{
                            // Handle scraped data filtering (existing logic)
                            // Check Laufzeit filter
                            const laufzeitMatch = currentLaufzeit === 'all' || meta.laufzeit === parseInt(currentLaufzeit);
                            
                            // Check Zinssatz type filter
                            let zinssatzMatch = true;
                            if (currentZinssatz === 'zinssatz') {{
                                zinssatzMatch = meta.type === 'zinssatz';
                            }} else if (currentZinssatz === 'effektiver') {{
                                zinssatzMatch = meta.type === 'effektiver';
                            }}
                            // 'beide' means both are shown, so zinssatzMatch stays true
                            
                            // Return true only if BOTH conditions match (AND logic)
                            visible.push(laufzeitMatch && zinssatzMatch);
                        }}
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
                    
                    document.querySelectorAll('.info-value')[0].textContent = '€' + run.kreditbetrag.toLocaleString('de-DE');
                    document.querySelectorAll('.info-value')[1].textContent = run.laufzeit_jahre + ' Jahre';
                    document.querySelectorAll('.info-value')[2].textContent = '€' + run.kaufpreis.toLocaleString('de-DE');
                    document.querySelectorAll('.info-value')[3].textContent = '€' + run.kaufnebenkosten.toLocaleString('de-DE');
                    document.querySelectorAll('.info-value')[4].textContent = '€' + run.eigenmittel.toLocaleString('de-DE');
                    document.querySelectorAll('.info-value')[5].textContent = run.haushalt_alter + ' Jahre';
                    document.querySelectorAll('.info-value')[6].textContent = '€' + run.haushalt_einkommen.toFixed(2) + '/Monat';
                    document.querySelectorAll('.info-value')[7].textContent = run.haushalt_nutzflaeche + ' m²';
                    
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
                
                // Toggle user offers visibility
                function toggleUserOffers() {{
                    // Simply reapply all filters to respect current filter settings
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
            <div class="run-info-grid">
                <div class="info-item">
                    <span class="info-label">Kreditbetrag:</span>
                    <span class="info-value">€{latest_run['kreditbetrag']:,.0f}</span>
                </div>
                <div class="info-item">
                    <span class="info-label">Laufzeit:</span>
                    <span class="info-value">{latest_run['laufzeit_jahre']} Jahre</span>
                </div>
                <div class="info-item">
                    <span class="info-label">Kaufpreis:</span>
                    <span class="info-value">€{latest_run['kaufpreis']:,.0f}</span>
                </div>
                <div class="info-item">
                    <span class="info-label">Kaufnebenkosten:</span>
                    <span class="info-value">€{latest_run['kaufnebenkosten']:,.0f}</span>
                </div>
                <div class="info-item">
                    <span class="info-label">Eigenmittel:</span>
                    <span class="info-value">€{latest_run['eigenmittel']:,.0f}</span>
                </div>
                <div class="info-item">
                    <span class="info-label">Haushalt Alter:</span>
                    <span class="info-value">{latest_run['haushalt_alter']} Jahre</span>
                </div>
                <div class="info-item">
                    <span class="info-label">Netto-Einkommen:</span>
                    <span class="info-value">€{latest_run['haushalt_einkommen']:,.2f}/Monat</span>
                </div>
                <div class="info-item">
                    <span class="info-label">Wohnnutzfläche:</span>
                    <span class="info-value">{latest_run['haushalt_nutzflaeche']} m²</span>
                </div>
            </div>
        </div>
        
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
    return True, png_base64


def generate_email_html(png_base64):
    """Generate simplified HTML for email with static PNG chart (no JavaScript)"""
    
    if not png_base64:
        print("[WARN] No PNG data available, cannot generate email HTML")
        return False
    
    # Get all runs data
    runs, all_variations = get_all_runs_data()
    
    if not runs:
        print("[WARN] No data found in database")
        return False
    
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
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 30px;
            border-left: 5px solid #3498db;
        }}
        .run-info h3 {{
            margin-top: 0;
            color: #2c3e50;
            font-size: 1.3em;
        }}
        .run-info-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 15px;
            margin-top: 15px;
        }}
        .info-item {{
            display: flex;
            justify-content: space-between;
            padding: 8px;
            background-color: white;
            border-radius: 4px;
        }}
        .info-label {{
            font-weight: bold;
            color: #34495e;
        }}
        .info-value {{
            color: #2c3e50;
            font-family: monospace;
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
                font-size: 1.1em;
            }}
            .run-info-grid {{
                grid-template-columns: 1fr;
                gap: 10px;
            }}
            .info-item {{
                padding: 6px;
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
    </style>
</head>
<body>
    <div class="container">
                <h1>🏠 Housing Loan Comparison</h1>
                <div class="subtitle">
                    Zinsentwicklung - 25 Jahre Laufzeit (Eff. Zinssatz)
                </div>
        
        <a href="https://smartprototypes.net/Bank_market_overview/bank_comparison_housing_loan_durchblicker.html" class="interactive-button" target="_blank" style="background-color: #667eea !important; color: white !important; text-decoration: none !important;">
            🔗 Go to Interactive Version
        </a>
        
        <div class="chart-container">
            <h2 style="color: #2c3e50; margin-bottom: 15px;">📊 Zinsentwicklung</h2>
            <img src="data:image/png;base64,{png_base64}" alt="Housing Loan Interest Rate Chart">
        </div>
        
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
            <div class="run-info-grid">
                <div class="info-item">
                    <span class="info-label">Kreditbetrag:</span>
                    <span class="info-value">€{latest_run['kreditbetrag']:,.0f}</span>
                </div>
                <div class="info-item">
                    <span class="info-label">Laufzeit:</span>
                    <span class="info-value">{latest_run['laufzeit_jahre']} Jahre</span>
                </div>
                <div class="info-item">
                    <span class="info-label">Kaufpreis:</span>
                    <span class="info-value">€{latest_run['kaufpreis']:,.0f}</span>
                </div>
                <div class="info-item">
                    <span class="info-label">Kaufnebenkosten:</span>
                    <span class="info-value">€{latest_run['kaufnebenkosten']:,.0f}</span>
                </div>
                <div class="info-item">
                    <span class="info-label">Eigenmittel:</span>
                    <span class="info-value">€{latest_run['eigenmittel']:,.0f}</span>
                </div>
                <div class="info-item">
                    <span class="info-label">Haushalt Alter:</span>
                    <span class="info-value">{latest_run['haushalt_alter']} Jahre</span>
                </div>
                <div class="info-item">
                    <span class="info-label">Netto-Einkommen:</span>
                    <span class="info-value">€{latest_run['haushalt_einkommen']:,.2f}/Monat</span>
                </div>
                <div class="info-item">
                    <span class="info-label">Wohnnutzfläche:</span>
                    <span class="info-value">{latest_run['haushalt_nutzflaeche']} m²</span>
                </div>
            </div>
        </div>
        
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
    success, png_base64 = generate_html()
    
    if success:
        print("\n[SUCCESS] Interactive HTML report generated successfully!")
        print(f"   [FILE] Web HTML: {HTML_PATH}")
        print(f"   [FILE] Chart PNG: {CHART_PNG_PATH}")
        
        # Generate email HTML (with static PNG)
        print("\n[INFO] Generating email-friendly HTML...")
        email_success = generate_email_html(png_base64)
        
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
