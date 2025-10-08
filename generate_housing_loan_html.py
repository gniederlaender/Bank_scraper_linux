#!/usr/bin/env python3
"""
Generate HTML page with interactive Plotly charts for housing loan data from durchblicker.at
"""

import sqlite3
from datetime import datetime
from pathlib import Path
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

DB_PATH = Path("/opt/Bankcomparison/austrian_banks_housing_loan.db")
HTML_PATH = Path("/opt/Bankcomparison/bank_comparison_housing_loan_durchblicker.html")


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
        print("⚠️ No data available for chart generation")
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
            }
        }
    )
    
    return chart_html, laufzeit_values, trace_metadata


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
    chart_html, laufzeit_values, trace_metadata = generate_interactive_chart()
    
    if not chart_html:
        print("⚠️ No data found in database")
        return False
    
    # Get all runs data
    runs, all_variations = get_all_runs_data()
    
    if not runs:
        print("⚠️ No data found in database")
        return False
    
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
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
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
            gap: 30px;
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
            gap: 10px;
        }}
        .control-label {{
            font-weight: bold;
            color: #2c3e50;
            font-size: 14px;
        }}
        select, button {{
            padding: 8px 15px;
            border: 2px solid #667eea;
            border-radius: 6px;
            font-size: 14px;
            font-family: 'Segoe UI', Arial;
            cursor: pointer;
            transition: all 0.3s;
        }}
        select {{
            background: white;
            color: #2c3e50;
        }}
        select:hover {{
            border-color: #764ba2;
        }}
        button {{
            background: white;
            color: #667eea;
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
                padding: 10px;
            }}
            .container {{
                padding: 15px;
            }}
            h1 {{
                font-size: 1.5em;
            }}
            .chart-container {{
                padding: 15px;
            }}
            table {{
                font-size: 0.85em;
            }}
            th, td {{
                padding: 8px 6px;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🏠 Housing Loan Comparison</h1>
        <div class="subtitle">
            Interactive Interest Rate Analysis
            <br>
            <span class="info-badge">📊 Combined Filters (Laufzeit AND Zinssatz)</span>
            <span class="info-badge">🔍 Click legend to toggle lines</span>
            <span class="info-badge">🖱️ Hover for details</span>
        </div>
        
        <div class="run-info">
            <h3>📊 Aktuellste Berechnung</h3>
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
        
        <div class="chart-container">
            <div class="chart-controls">
                <div class="control-group">
                    <span class="control-label">Laufzeit:</span>
                    <select id="laufzeit-filter">
                        <option value="all">Alle Laufzeiten</option>
{f''.join([f'                        <option value="{lz}">{lz} Jahre</option>\n' for lz in laufzeit_values])}                    </select>
                </div>
                <div class="control-group">
                    <span class="control-label">Anzeigen:</span>
                    <button id="btn-beide" class="active" onclick="setZinssatzFilter('beide')">Beide</button>
                    <button id="btn-zinssatz" onclick="setZinssatzFilter('zinssatz')">Nur Zinssatz</button>
                    <button id="btn-effektiver" onclick="setZinssatzFilter('effektiver')">Nur Eff. Zinssatz</button>
                </div>
            </div>
            
            {chart_html}
            
            <script>
                // Store trace metadata
                const traceMetadata = {str(trace_metadata)};
                
                // Store table data for each Laufzeit
                const tableData = {str({int(k): {'run': v['run'], 'variations': v['variations']} for k, v in latest_by_laufzeit.items()})};
                
                // Current filter states
                let currentLaufzeit = 'all';
                let currentZinssatz = 'beide';
                
                // Apply combined filters (chart + tables)
                function applyFilters() {{
                    // Update chart visibility
                    const visible = traceMetadata.map(meta => {{
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
                        return laufzeitMatch && zinssatzMatch;
                    }});
                    
                    // Update the Plotly chart
                    Plotly.restyle('plotly-chart', {{'visible': visible}});
                    
                    // Update tables based on Laufzeit
                    updateTables();
                }}
                
                // Update tables based on current Laufzeit filter
                function updateTables() {{
                    if (currentLaufzeit === 'all') {{
                        // Show latest overall run (could be any Laufzeit)
                        const latestLaufzeit = {latest_run['laufzeit_jahre']};
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
                    document.querySelector('.run-info h3').textContent = '📊 ' + headerText;
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
                                    <td>${{v.besicherung}}</td>
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
                    
                    // Build Kostenübersicht table
                    const baseline = variations.find(v => v.fixierung_jahre === 0 && v.gesamtbetrag);
                    const baselineTotal = baseline ? baseline.gesamtbetrag : 0;
                    
                    let kostenTable = '';
                    variations.forEach(v => {{
                        if (v.rate) {{
                            const diff = v.gesamtbetrag - baselineTotal;
                            const diffClass = Math.abs(diff) > 1000 ? 'highlight' : '';
                            const diffSign = diff > 0 ? '+' : '';
                            const diffColor = diff > 0 ? '#e74c3c' : '#27ae60';
                            
                            kostenTable += `
                                <tr class="${{diffClass}}">
                                    <td class="fixierung-cell">${{v.fixierung_jahre}}J</td>
                                    <td>€${{v.auszahlungsbetrag.toLocaleString('de-DE', {{minimumFractionDigits: 2, maximumFractionDigits: 2}})}}</td>
                                    <td>€${{v.einberechnete_kosten.toLocaleString('de-DE', {{minimumFractionDigits: 2, maximumFractionDigits: 2}})}}</td>
                                    <td>€${{v.kreditbetrag.toLocaleString('de-DE', {{minimumFractionDigits: 2, maximumFractionDigits: 2}})}}</td>
                                    <td style="font-weight: bold;">€${{v.gesamtbetrag.toLocaleString('de-DE', {{minimumFractionDigits: 2, maximumFractionDigits: 2}})}}</td>
                                    <td style="color: ${{diffColor}};">${{diffSign}}€${{diff.toLocaleString('de-DE', {{minimumFractionDigits: 2, maximumFractionDigits: 2}})}}</td>
                                </tr>`;
                        }}
                    }});
                    document.querySelector('#kosten-tbody').innerHTML = kostenTable;
                    
                    // Update timestamp with run ID
                    const timestampDiv = document.querySelector('.timestamp');
                    const currentTime = timestampDiv.innerHTML.split('<br>')[0];
                    timestampDiv.innerHTML = currentTime + '<br>Data Source: Housing Loan Database | Run ID: ' + run.id + 
                        '<br><small>💡 Tip: Filters work together - selecting "20 Jahre" + "Nur Eff. Zinssatz" shows ONLY Effektiver Zinssatz for 20 Jahre Laufzeit</small>';
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
            </script>
        </div>
        
        <div class="table-container">
            <h2 style="color: #2c3e50; margin-bottom: 20px;">📋 Finanzierungsdetails - Aktuellste Konditionen</h2>
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
                        <th>Besicherung</th>
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
        
        <div class="table-container">
            <h2 style="color: #2c3e50; margin-bottom: 20px;">💰 Kostenübersicht</h2>
            <table>
                <thead>
                    <tr>
                        <th>Fixierung</th>
                        <th>Auszahlungsbetrag</th>
                        <th>Einberechnete Kosten</th>
                        <th>Kreditbetrag</th>
                        <th>Zu zahlender Gesamtbetrag</th>
                        <th>Differenz zu 0J</th>
                    </tr>
                </thead>
                <tbody id="kosten-tbody">
'''
    
    # Calculate baseline (0 years Fixierung) for comparison
    baseline_var = next((v for v in latest_variations if v['fixierung_jahre'] == 0 and v['gesamtbetrag']), None)
    baseline_gesamtbetrag = baseline_var['gesamtbetrag'] if baseline_var else 0
    
    for var in latest_variations:
        if var['rate']:
            diff = var['gesamtbetrag'] - baseline_gesamtbetrag if baseline_gesamtbetrag else 0
            diff_class = 'highlight' if abs(diff) > 1000 else ''
            diff_sign = '+' if diff > 0 else ''
            
            html_content += f'''
                    <tr class="{diff_class}">
                        <td class="fixierung-cell">{var['fixierung_jahre']}J</td>
                        <td>€{var['auszahlungsbetrag']:,.2f}</td>
                        <td>€{var['einberechnete_kosten']:,.2f}</td>
                        <td>€{var['kreditbetrag']:,.2f}</td>
                        <td style="font-weight: bold;">€{var['gesamtbetrag']:,.2f}</td>
                        <td style="color: {'#e74c3c' if diff > 0 else '#27ae60'};">{diff_sign}€{diff:,.2f}</td>
                    </tr>
'''
    
    html_content += f'''
                </tbody>
            </table>
        </div>
        
        <div class="timestamp">
            Last Updated: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}<br>
            Data Source: Housing Loan Database | Latest Run ID: {latest_run['id']}<br>
            <small>💡 Tip: Filters work together - selecting "20 Jahre" + "Nur Eff. Zinssatz" shows ONLY Effektiver Zinssatz for 20 Jahre Laufzeit</small>
        </div>
    </div>
</body>
</html>
'''
    
    # Write to file
    with open(HTML_PATH, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"✓ HTML page generated: {HTML_PATH}")
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
        print("⚠️  View 'housing_loan_chart_ready' does not exist!")
        print("   Please run: python3 create_housing_loan_view.py")
        exit(1)
    
    success = generate_html()
    
    if success:
        print("\n✅ HTML report generated successfully!")
        print(f"   📄 HTML: {HTML_PATH}")
        print(f"\n   Open in browser: file://{HTML_PATH.absolute()}")
        print("\n   🎯 Features:")
        print("      • Laufzeit dropdown filter (All, 15, 20, 25, 30 Jahre)")
        print("      • Toggle Zinssatz / Effektiver Zinssatz")
        print("      • Interactive legend (click to show/hide)")
        print("      • Zoom, pan, hover for details")
    else:
        print("\n❌ HTML generation failed!")
