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

# Get paths from environment or use relative paths
BASE_DIR = Path(os.getenv('BANKCOMPARISON_BASE_DIR', '.'))
DB_PATH = BASE_DIR / os.getenv('CONSUMER_LOAN_DB_PATH', 'austrian_banks.db')
HTML_PATH = BASE_DIR / os.getenv('CONSUMER_LOAN_HTML_PATH', 'bank_comparison_consumer_loan.html')
HTML_EMAIL_PATH = BASE_DIR / os.getenv('CONSUMER_LOAN_EMAIL_HTML_PATH', 'bank_comparison_consumer_loan_email.html')
CHART_PNG_PATH = BASE_DIR / os.getenv('CONSUMER_LOAN_CHART_PNG_PATH', 'consumer_loan_chart.png')


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
    
    # Convert timestamp to datetime
    df['date_scraped'] = pd.to_datetime(df['date_scraped'])
    
    # Define colors for each bank
    colors = {
        'raiffeisen': '#1f77b4',   # Blue
        'bawag': '#ff7f0e',          # Orange
        'bank99': '#2ca02c',         # Green
        'erste': '#d62728'           # Red
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
        
        # Trace for Rate (solid line)
        fig.add_trace(go.Scatter(
            x=data['date_scraped'],
            y=data['rate_numeric'],
            mode='lines+markers',
            name=f'{bank.capitalize()} - Rate',
            line=dict(color=color, width=2.5, dash='solid'),
            marker=dict(size=8, symbol='circle'),
            legendgroup=f'bank_{bank}',
            hovertemplate=(
                f'<b>{bank.capitalize()}</b><br>'
                'Datum: %{x|%d.%m.%Y}<br>'
                'Rate: %{y:.3f}%<br>'
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
            marker=dict(size=8, symbol='square'),
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
    
    # Update layout
    fig.update_layout(
        title={
            'text': '🏦 Konsumkredit Zinsentwicklung - Interaktive Analyse',
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
    """Generate static PNG chart using matplotlib for email embedding - Default: Eff. Zinssatz only"""
    
    # Create figure
    plt.figure(figsize=(14, 7))
    
    # Default: Only show Effektiver Zinssatz
    show_rate = False  # Only show Effektiver Zinssatz
    
    # Plot data for each bank
    for bank in bank_names:
        data = df[df['bank_name'] == bank].copy()
        
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
    
    # Customize plot
    plt.title('Konsumkredit Zinsentwicklung (Effektiver Zinssatz)', 
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
        button {{
            padding: 10px 12px;
            border: 2px solid #667eea;
            border-radius: 6px;
            font-size: 14px;
            font-family: 'Segoe UI', Arial;
            cursor: pointer;
            transition: all 0.3s;
            min-height: 40px;
        }}
        button.active {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }}
        button:hover {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
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
        .bank-name {{
            font-weight: bold;
            color: #2c3e50;
            background-color: #e8f4f8 !important;
        }}
        .timestamp {{
            text-align: center;
            color: #7f8c8d;
            font-size: 0.9em;
            margin-top: 30px;
            padding-top: 20px;
            border-top: 2px solid #ecf0f1;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🏦 Consumer Loan Comparison</h1>
        <div class="subtitle">Konsumkredit - Interaktive Zinsentwicklung</div>
        
        <div class="chart-container">
            <div class="chart-controls">
                <div class="control-group">
                    <span class="control-label">Anzeigen:</span>
                    <button id="btn-beide" onclick="setZinssatzFilter('beide')">Beide</button>
                    <button id="btn-rate" onclick="setZinssatzFilter('rate')">Nur Zinssatz</button>
                    <button id="btn-effektiver" class="active" onclick="setZinssatzFilter('effektiver')">Nur Eff. Zinssatz</button>
                </div>
            </div>
            
            {chart_html}
            
            <script>
                // Store trace metadata
                const traceMetadata = {json.dumps(trace_metadata)};
                
                // Current filter state
                let currentZinssatz = 'effektiver';
                
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
                
                // Apply initial filters
                setTimeout(() => {{
                    applyFilters();
                }}, 1500);
            </script>
        </div>
        
        <div class="table-container">
            <h2 style="color: #2c3e50; margin-bottom: 20px;">📋 Aktuelle Konditionen</h2>
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
    """Generate simplified HTML for email with static PNG chart (no JavaScript)"""
    
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
        .bank-name {{
            font-weight: bold;
            color: #2c3e50;
            background-color: #e8f4f8 !important;
        }}
        .timestamp {{
            text-align: center;
            color: #7f8c8d;
            font-size: 0.9em;
            margin-top: 30px;
            padding-top: 20px;
            border-top: 2px solid #ecf0f1;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🏦 Consumer Loan Comparison</h1>
        <div class="subtitle">Konsumkredit - Zinsentwicklung (Effektiver Zinssatz)</div>
        
        <a href="https://smartprototypes.net/Bank_market_overview/bank_comparison_consumer_loan.html" class="interactive-button" target="_blank" style="background-color: #667eea !important; color: white !important; text-decoration: none !important;">
            🔗 Go to Interactive Version
        </a>
        
        <div class="chart-container">
            <h2 style="color: #2c3e50; margin-bottom: 15px;">📊 Zinsentwicklung</h2>
            <img src="data:image/png;base64,{png_base64}" alt="Consumer Loan Interest Rate Chart">
        </div>
        
        <div class="table-container">
            <h2 style="color: #2c3e50; margin-bottom: 20px;">📋 Aktuelle Konditionen</h2>
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

