#!/usr/bin/env python3
"""
Generate HTML page with interactive Plotly charts for consumer loan data
Similar to generate_housing_loan_html.py but for consumer loans
"""

import sqlite3
import os
from datetime import datetime
from pathlib import Path
import pandas as pd
import plotly.graph_objects as go
import json
import base64
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# Try to load dotenv if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not available, will use environment variables

# Get paths from environment or use relative paths
BASE_DIR = Path(os.getenv('BANKCOMPARISON_BASE_DIR', '.'))
DB_PATH = BASE_DIR / os.getenv('CONSUMER_LOAN_DB_PATH', 'austrian_banks.db')
HTML_PATH = BASE_DIR / os.getenv('CONSUMER_LOAN_HTML_PATH', 'bank_comparison_consumer_loan.html')
HTML_EMAIL_PATH = BASE_DIR / os.getenv('CONSUMER_LOAN_EMAIL_HTML_PATH', 'bank_comparison_consumer_loan_email.html')
CHART_PNG_PATH = BASE_DIR / os.getenv('CONSUMER_LOAN_CHART_PNG_PATH', 'consumer_loan_chart.png')

# Shared design tokens for Plotly charts, kept in sync with the CSS custom
# properties in generate_html()'s <style> block so charts and page chrome match
# (same tokens as generate_housing_loan_html.py, for a consistent look across pages).
PLOTLY_FONT = '-apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif'
COLOR_TEXT = '#1b2733'
COLOR_TEXT_MUTED = '#5b6b78'
COLOR_GRID = '#e2e8ee'


def generate_interactive_chart():
    """
    Generate interactive Plotly chart for consumer loan data with:
    - Bank comparison over time
    - Interactive legend, zoom, pan, hover
    """
    conn = sqlite3.connect(str(DB_PATH))
    
    # Query data from the view
    query = """
    SELECT 
        bank_name,
        date_scraped,
        rate_numeric,
        effektiver_jahreszins_numeric,
        rate,
        effektiver_jahreszins,
        monatliche_rate,
        nettokreditbetrag
    FROM consumer_loan_chart_ready
    ORDER BY date_scraped, bank_name
    """
    
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    if df.empty:
        print("[WARN] No data available for chart generation")
        return None, []
    
    # Convert timestamp to datetime. format='mixed' guards against rows
    # written with different separators (e.g. a period where date_scraped
    # was stored via datetime.isoformat()'s "T" separator instead of the
    # historical "YYYY-MM-DD HH:MM:SS.ffffff" space-separated format) so one
    # inconsistent row can't crash the whole report.
    df['date_scraped'] = pd.to_datetime(df['date_scraped'], format='mixed')
    
    # Colors for each bank - modern, distinguishable palette
    colors = {
        'raiffeisen': '#2563eb',   # Blue
        'bawag': '#d97706',        # Amber
        'bank99': '#059669',       # Emerald
        'erste': '#dc2626',        # Red
        'santander': '#7c3aed',    # Violet
        'bankaustria': '#db2777'   # Pink
    }
    
    # Get unique banks
    bank_names = sorted(df['bank_name'].unique())
    
    print(f"Creating interactive chart with {len(bank_names)} banks...")
    
    # Create figure
    fig = go.Figure()
    
    # Add traces for each bank
    for bank in bank_names:
        data = df[df['bank_name'] == bank].copy()
        
        if data.empty:
            continue
        
        data = data.sort_values('date_scraped')
        color = colors.get(bank, '#333333')
        
        # Trace for Sollzins (solid line)
        fig.add_trace(go.Scatter(
            x=data['date_scraped'],
            y=data['rate_numeric'],
            mode='lines+markers',
            name=f'{bank.capitalize()} - Sollzins',
            line=dict(color=color, width=3, dash='solid'),
            marker=dict(size=9, symbol='circle', line=dict(width=1, color='white')),
            legendgroup=f'bank_{bank}',
            hovertemplate=(
                f'<b>{bank.capitalize()}</b><br>'
                'Datum: %{x|%d.%m.%Y}<br>'
                'Sollzins: %{y:.3f}%<br>'
                '<extra></extra>'
            ),
            visible=True,
            customdata=[['rate', bank]]
        ))

        # Trace for Effektiver Zinssatz (dashed line)
        fig.add_trace(go.Scatter(
            x=data['date_scraped'],
            y=data['effektiver_jahreszins_numeric'],
            mode='lines+markers',
            name=f'{bank.capitalize()} - Eff. Zins',
            line=dict(color=color, width=2.5, dash='dash'),
            marker=dict(size=8, symbol='square', line=dict(width=1, color='white')),
            legendgroup=f'bank_{bank}',
            hovertemplate=(
                f'<b>{bank.capitalize()}</b><br>'
                'Datum: %{x|%d.%m.%Y}<br>'
                'Eff. Zinssatz: %{y:.3f}%<br>'
                '<extra></extra>'
            ),
            visible=True,
            customdata=[['effektiver', bank]]
        ))
    
    # Store trace metadata for JavaScript filtering
    trace_metadata = []
    for trace in fig.data:
        if trace.customdata:
            trace_metadata.append({
                'type': trace.customdata[0][0],
                'bank': trace.customdata[0][1]
            })
        else:
            trace_metadata.append({'type': None, 'bank': None})
    
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
        div_id='plotly-chart',
        config={
            'displayModeBar': True,
            'displaylogo': False,
            'modeBarButtonsToRemove': ['select2d', 'lasso2d'],
            'toImageButtonOptions': {
                'format': 'png',
                'filename': 'consumer_loan_chart',
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
        png_base64 = generate_static_png_chart(df, bank_names, colors)
        print(f"[OK] Chart PNG saved: {CHART_PNG_PATH}")
    except Exception as e:
        print(f"[WARN] Warning: Could not export PNG: {e}")
        print("   (Email version will be generated without chart)")
        png_base64 = None
    
    return chart_html, trace_metadata, png_base64


def generate_static_png_chart(df, bank_names, colors):
    """Generate static PNG chart using matplotlib for email embedding - Default: Eff. Zinssatz only, last 12 months"""

    from datetime import timedelta

    # Filter to last 12 months
    twelve_months_ago = datetime.now() - timedelta(days=365)
    df_filtered = df[df['date_scraped'] >= twelve_months_ago].copy()

    if df_filtered.empty:
        print("[WARN] No data in last 12 months, using all available data")
        df_filtered = df.copy()

    # Create figure
    plt.figure(figsize=(14, 7))

    # Default: Only show Effektiver Zinssatz
    show_rate = False  # Only show Effektiver Zinssatz

    # Plot data for each bank
    for bank in bank_names:
        data = df_filtered[df_filtered['bank_name'] == bank].copy()
        
        if data.empty:
            continue
        
        data = data.sort_values('date_scraped')
        color = colors.get(bank, '#333333')
        
        # Only plot Effektiver Zinssatz (dashed line)
        plt.plot(
            data['date_scraped'],
            data['effektiver_jahreszins_numeric'],
            marker='s',
            linewidth=2.5,
            markersize=5,
            linestyle='--',
            color=color,
            label=f'{bank.capitalize()} - Eff. Zinssatz',
            alpha=0.8
        )
    
    # Customize plot with date range in title
    date_from = twelve_months_ago.strftime('%d.%m.%Y')
    date_to = datetime.now().strftime('%d.%m.%Y')
    plt.title(f'Konsumkredit Zinsentwicklung ({date_from} - {date_to})',
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
               frameon=True, shadow=True, fontsize=9)
    
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


def get_latest_data():
    """Get the latest data for each bank from the database"""
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    # Get latest entry for each bank
    cursor.execute("""
        WITH latest_entries AS (
            SELECT bank_name, MAX(date_scraped) as latest_date
            FROM interest_rates
            GROUP BY bank_name
        )
        SELECT i.*
        FROM interest_rates i
        INNER JOIN latest_entries le 
        ON i.bank_name = le.bank_name 
        AND i.date_scraped = le.latest_date
        ORDER BY i.bank_name
    """)
    
    rows = cursor.fetchall()
    column_names = [description[0] for description in cursor.description]
    
    result = []
    for row in rows:
        result.append(dict(zip(column_names, row)))
    
    conn.close()
    
    return result


def generate_html():
    """Generate HTML page with interactive Plotly chart and data table"""
    
    # Generate chart
    chart_html, trace_metadata, png_base64 = generate_interactive_chart()
    
    if not chart_html:
        print("[WARN] No data found in database")
        return False, None
    
    # Get latest data for table
    latest_data = get_latest_data()
    
    if not latest_data:
        print("[WARN] No data found in database")
        return False, None
    
    # Create HTML content
    html_content = f'''<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bank Comparison - Consumer Loan Analysis (Interactive)</title>
    <style>
        :root {{
            --color-bg: #f2f5f7;
            --color-surface: #ffffff;
            --color-primary: #0f3b52;
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
        details.filters-accordion {{
            background: var(--color-accent-light);
            border-radius: var(--radius-md);
            margin-bottom: 18px;
            border: 1px solid var(--color-border);
            overflow: hidden;
        }}
        details.filters-accordion > summary {{
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
        details.filters-accordion > summary::-webkit-details-marker {{
            display: none;
        }}
        details.filters-accordion > summary::after {{
            content: '▾';
            transition: transform 0.2s;
            color: var(--color-accent);
            font-size: 1.1em;
        }}
        details[open].filters-accordion > summary::after {{
            transform: rotate(180deg);
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
        .control-label {{
            font-weight: 600;
            color: var(--color-primary);
            font-size: 13px;
            white-space: nowrap;
        }}
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
        .bank-name {{
            font-weight: 700;
            color: var(--color-primary);
            background-color: var(--color-accent-light) !important;
            border-left: 4px solid var(--color-accent);
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
                padding: 8px;
            }}
            .container {{
                padding: 12px;
                border-radius: var(--radius-md);
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
            .segmented-control {{
                width: 100%;
                justify-content: stretch;
            }}
            .segmented-control button {{
                flex: 1;
            }}
            #plotly-chart {{
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
            <a href="bank_comparison_housing_loan_durchblicker.html" class="nav-tab">🏠 Housing Loans</a>
            <a href="#" class="nav-tab active">🏦 Consumer Loans</a>
        </div>
        <h1>🏦 Consumer Loan Comparison</h1>
        <div class="subtitle">Konsumkredit - Interaktive Zinsentwicklung</div>

        <script>
            document.addEventListener('DOMContentLoaded', function() {{
                document.querySelectorAll('details.filters-accordion').forEach(function(d) {{
                    d.open = window.innerWidth > 768;
                }});
            }});
        </script>

        <div class="chart-container">
            <div class="chart-title">🏦 Konsumkredit Zinsentwicklung</div>
            <details class="filters-accordion">
                <summary>🔧 Filter &amp; Anzeige</summary>
                <div class="accordion-body">
                <div class="chart-controls">
                <div class="control-group">
                    <span class="control-label">Anzeigen:</span>
                    <div class="segmented-control">
                        <button id="btn-beide" onclick="setZinssatzFilter('beide')">Beide</button>
                        <button id="btn-rate" class="active" onclick="setZinssatzFilter('rate')">Nur Sollzins</button>
                        <button id="btn-effektiver" onclick="setZinssatzFilter('effektiver')">Nur Eff. Zinssatz</button>
                    </div>
                </div>
                </div>
                </div>
            </details>

            {chart_html}
            
            <script>
                // Store trace metadata
                const traceMetadata = {json.dumps(trace_metadata)};
                
                // Current filter state
                let currentZinssatz = 'rate';
                
                // Apply filters
                function applyFilters() {{
                    const visible = traceMetadata.map(meta => {{
                        let zinssatzMatch = true;
                        if (currentZinssatz === 'rate') {{
                            zinssatzMatch = meta.type === 'rate';
                        }} else if (currentZinssatz === 'effektiver') {{
                            zinssatzMatch = meta.type === 'effektiver';
                        }}
                        return zinssatzMatch;
                    }});
                    
                    Plotly.restyle('plotly-chart', {{'visible': visible}});
                }}
                
                // Zinssatz button click handler
                function setZinssatzFilter(type) {{
                    currentZinssatz = type;
                    
                    // Update button styling
                    document.getElementById('btn-beide').classList.remove('active');
                    document.getElementById('btn-rate').classList.remove('active');
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
                
                // Apply initial filters
                setTimeout(() => {{
                    applyFilters();
                }}, 1500);
            </script>
        </div>

        <div class="table-container">
            <h2 style="margin-bottom: 20px;">📋 Aktuelle Konditionen</h2>
            <table>
                <thead>
                    <tr>
                        <th>Bank</th>
                        <th>Sollzinssatz</th>
                        <th>Effektiver Jahreszins</th>
                        <th>Nettokreditbetrag</th>
                        <th>Vertragslaufzeit</th>
                        <th>Monatliche Rate</th>
                        <th>Gesamtbetrag</th>
                        <th>Min./Max. Betrag</th>
                        <th>Min./Max. Laufzeit</th>
                    </tr>
                </thead>
                <tbody>
'''
    
    # Add table rows
    for row in latest_data:
        html_content += f'''
                    <tr>
                        <td class="bank-name">{row['bank_name'].capitalize()}</td>
                        <td>{row.get('rate', '-')}</td>
                        <td>{row.get('effektiver_jahreszins', '-')}</td>
                        <td>{row.get('nettokreditbetrag', '-')}</td>
                        <td>{row.get('vertragslaufzeit', '-')}</td>
                        <td>{row.get('monatliche_rate', '-')}</td>
                        <td>{row.get('gesamtbetrag', '-')}</td>
                        <td>{row.get('min_betrag', '-')} / {row.get('max_betrag', '-')}</td>
                        <td>{row.get('min_laufzeit', '-')} / {row.get('max_laufzeit', '-')}</td>
                    </tr>
'''
    
    html_content += f'''
                </tbody>
            </table>
        </div>
        
        <div class="timestamp">
            Last Updated: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}<br>
            Data Source: Consumer Loan Database
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
    """
    Generate static HTML for email (no JavaScript, so no filter accordion or
    interactive Plotly chart). Mirrors the redesigned web page's design
    tokens, chart-title/table markup and "Nur Sollzins" default wording.
    """

    if not png_base64:
        print("[WARN] No PNG data available, cannot generate email HTML")
        return False

    # Get latest data for table
    latest_data = get_latest_data()

    if not latest_data:
        print("[WARN] No data found in database")
        return False

    # Create simplified HTML content for email (no JavaScript)
    html_content = f'''<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bank Comparison - Consumer Loan Analysis</title>
    <style>
        :root {{
            --color-bg: #f2f5f7;
            --color-surface: #ffffff;
            --color-primary: #0f3b52;
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
            background-color: var(--color-primary) !important;
            color: white !important;
            text-decoration: none !important;
            border-radius: var(--radius-sm);
            font-size: 1.1em;
            font-weight: bold;
            text-align: center;
            box-shadow: var(--shadow-sm);
        }}
        .interactive-button:visited, .interactive-button:link {{
            color: white !important;
            text-decoration: none !important;
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
        .bank-name {{
            font-weight: 700;
            color: var(--color-primary);
            background-color: var(--color-accent-light) !important;
            border-left: 4px solid var(--color-accent);
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
                min-width: 560px;
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
        <h1>🏦 Consumer Loan Comparison</h1>
        <div class="subtitle">Konsumkredit - Sollzins-Entwicklung</div>

        <a href="https://smartprototypes.net/Bank_market_overview/bank_comparison_consumer_loan.html" class="interactive-button" target="_blank">
            🔗 Zu den interaktiven Charts
        </a>

        <div class="chart-container">
            <div class="chart-title">🏦 Konsumkredit Zinsentwicklung</div>
            <img src="data:image/png;base64,{png_base64}" alt="Consumer Loan Interest Rate Chart">
        </div>

        <div class="table-container">
            <h2>📋 Aktuelle Konditionen</h2>
            <table>
                <thead>
                    <tr>
                        <th>Bank</th>
                        <th>Sollzinssatz</th>
                        <th>Effektiver Jahreszins</th>
                        <th>Nettokreditbetrag</th>
                        <th>Vertragslaufzeit</th>
                        <th>Monatliche Rate</th>
                        <th>Gesamtbetrag</th>
                        <th>Min./Max. Betrag</th>
                        <th>Min./Max. Laufzeit</th>
                    </tr>
                </thead>
                <tbody>
'''
    
    # Add table rows
    for row in latest_data:
        html_content += f'''
                    <tr>
                        <td class="bank-name">{row['bank_name'].capitalize()}</td>
                        <td>{row.get('rate', '-')}</td>
                        <td>{row.get('effektiver_jahreszins', '-')}</td>
                        <td>{row.get('nettokreditbetrag', '-')}</td>
                        <td>{row.get('vertragslaufzeit', '-')}</td>
                        <td>{row.get('monatliche_rate', '-')}</td>
                        <td>{row.get('gesamtbetrag', '-')}</td>
                        <td>{row.get('min_betrag', '-')} / {row.get('max_betrag', '-')}</td>
                        <td>{row.get('min_laufzeit', '-')} / {row.get('max_laufzeit', '-')}</td>
                    </tr>
'''
    
    html_content += f'''
                </tbody>
            </table>
        </div>
        
        <div class="timestamp">
            Last Updated: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}<br>
            Data Source: Consumer Loan Database
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
    print("Generating Consumer Loan HTML Report (Interactive Plotly)")
    print("="*60 + "\n")
    
    # Check if view exists
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='view' AND name='consumer_loan_chart_ready'")
    view_exists = cursor.fetchone()
    conn.close()
    
    if not view_exists:
        print("[WARN] View 'consumer_loan_chart_ready' does not exist!")
        print("   Please run: python create_consumer_loan_view.py")
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
        print("      • Toggle Zinssatz / Effektiver Zinssatz")
        print("      • Interactive legend (click to show/hide)")
        print("      • Zoom, pan, hover for details")
        print("\n   [FEATURES] Email Version Features:")
        print("      • Static PNG chart (works in all email clients)")
        print("      • No JavaScript required")
        print("      • Embedded base64 image")
        print("      • Link to interactive version")
    else:
        print("\n[ERROR] HTML generation failed!")

