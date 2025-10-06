#!/usr/bin/env python3
"""
Create a database view with cleaned numeric data for charting
"""

import sqlite3

def create_chart_view():
    """Create a view with cleaned numeric data for charting"""
    
    conn = sqlite3.connect('/opt/Bankcomparison/austrian_banks.db')
    cursor = conn.cursor()
    
    print("Creating chart-ready view...")
    
    # Drop view if it exists
    cursor.execute("DROP VIEW IF EXISTS interest_rates_chart_ready")
    
    # Create the view with cleaned numeric data
    create_view_sql = """
    CREATE VIEW interest_rates_chart_ready AS
    SELECT 
        id,
        bank_name,
        product_name,
        currency,
        date_scraped,
        source_url,
        full_text,
        
        -- Clean percentages (rate, effektiver_jahreszins)
        CAST(REPLACE(REPLACE(REPLACE(rate, '%', ''), ',', '.'), ' ', '') AS REAL) as rate_numeric,
        CAST(REPLACE(REPLACE(REPLACE(effektiver_jahreszins, '%', ''), ',', '.'), ' ', '') AS REAL) as effektiver_jahreszins_numeric,
        
        -- Clean currency amounts (nettokreditbetrag, gesamtbetrag, monatliche_rate)
        -- Handle German format: 10.000,00 -> 10000.00
        CAST(
            CASE 
                WHEN nettokreditbetrag LIKE '%.%,%' THEN
                    -- German format: remove thousand separators, replace comma with dot
                    REPLACE(REPLACE(REPLACE(REPLACE(nettokreditbetrag, '€', ''), 'Euro', ''), '.', ''), ',', '.')
                WHEN nettokreditbetrag LIKE '%,%' THEN
                    -- Just comma decimal separator
                    REPLACE(REPLACE(REPLACE(nettokreditbetrag, '€', ''), 'Euro', ''), ',', '.')
                ELSE
                    -- Already in correct format, just remove currency symbols
                    REPLACE(REPLACE(nettokreditbetrag, '€', ''), 'Euro', '')
            END AS REAL
        ) as nettokreditbetrag_numeric,
        
        CAST(
            CASE 
                WHEN gesamtbetrag LIKE '%.%,%' THEN
                    REPLACE(REPLACE(REPLACE(REPLACE(gesamtbetrag, '€', ''), 'Euro', ''), '.', ''), ',', '.')
                WHEN gesamtbetrag LIKE '%,%' THEN
                    REPLACE(REPLACE(REPLACE(gesamtbetrag, '€', ''), 'Euro', ''), ',', '.')
                ELSE
                    REPLACE(REPLACE(gesamtbetrag, '€', ''), 'Euro', '')
            END AS REAL
        ) as gesamtbetrag_numeric,
        
        CAST(
            CASE 
                WHEN monatliche_rate LIKE '%.%,%' THEN
                    REPLACE(REPLACE(REPLACE(REPLACE(monatliche_rate, '€', ''), 'Euro', ''), '.', ''), ',', '.')
                WHEN monatliche_rate LIKE '%,%' THEN
                    REPLACE(REPLACE(REPLACE(monatliche_rate, '€', ''), 'Euro', ''), ',', '.')
                ELSE
                    REPLACE(REPLACE(monatliche_rate, '€', ''), 'Euro', '')
            END AS REAL
        ) as monatliche_rate_numeric,
        
        -- Clean time periods (convert to months)
        CASE 
            WHEN vertragslaufzeit LIKE '%Jahre%' THEN 
                CAST(REPLACE(REPLACE(vertragslaufzeit, ' Jahre', ''), ' ', '') AS INTEGER) * 12
            WHEN vertragslaufzeit LIKE '%Monate%' THEN 
                CAST(REPLACE(REPLACE(vertragslaufzeit, ' Monate', ''), ' ', '') AS INTEGER)
            ELSE 
                CAST(vertragslaufzeit AS INTEGER)
        END as vertragslaufzeit_numeric,
        
        -- Clean min/max amounts
        CAST(REPLACE(REPLACE(REPLACE(
            min_betrag, '.', ''), ',', '.'), ' ', ''
        ) AS REAL) as min_betrag_numeric,
        
        CAST(REPLACE(REPLACE(REPLACE(
            max_betrag, '.', ''), ',', '.'), ' ', ''
        ) AS REAL) as max_betrag_numeric,
        
        -- Clean min/max time periods (convert to months)
        CASE 
            WHEN min_laufzeit LIKE '%Jahre%' THEN 
                CAST(REPLACE(REPLACE(min_laufzeit, ' Jahre', ''), ' ', '') AS INTEGER) * 12
            WHEN min_laufzeit LIKE '%Monate%' THEN 
                CAST(REPLACE(REPLACE(min_laufzeit, ' Monate', ''), ' ', '') AS INTEGER)
            ELSE 
                CAST(min_laufzeit AS INTEGER)
        END as min_laufzeit_numeric,
        
        CASE 
            WHEN max_laufzeit LIKE '%Jahre%' THEN 
                CAST(REPLACE(REPLACE(max_laufzeit, ' Jahre', ''), ' ', '') AS INTEGER) * 12
            WHEN max_laufzeit LIKE '%Monate%' THEN 
                CAST(REPLACE(REPLACE(max_laufzeit, ' Monate', ''), ' ', '') AS INTEGER)
            ELSE 
                CAST(max_laufzeit AS INTEGER)
        END as max_laufzeit_numeric,
        
        -- Keep original text fields for reference
        rate,
        effektiver_jahreszins,
        nettokreditbetrag,
        gesamtbetrag,
        vertragslaufzeit,
        monatliche_rate,
        min_betrag,
        max_betrag,
        min_laufzeit,
        max_laufzeit
    FROM interest_rates
    """
    
    try:
        cursor.execute(create_view_sql)
        conn.commit()
        print("✓ View 'interest_rates_chart_ready' created successfully!")
        
        # Test the view with a sample query
        cursor.execute("SELECT COUNT(*) FROM interest_rates_chart_ready")
        count = cursor.fetchone()[0]
        print(f"✓ View contains {count} records")
        
        # Show sample of cleaned data
        cursor.execute("""
            SELECT bank_name, rate, rate_numeric, effektiver_jahreszins, effektiver_jahreszins_numeric, 
                   nettokreditbetrag, nettokreditbetrag_numeric
            FROM interest_rates_chart_ready 
            ORDER BY date_scraped DESC 
            LIMIT 5
        """)
        
        print("\nSample cleaned data:")
        print("-" * 80)
        for row in cursor.fetchall():
            print(f"Bank: {row[0]}")
            print(f"  Rate: '{row[1]}' -> {row[2]}")
            print(f"  Eff. Zins: '{row[3]}' -> {row[4]}")
            print(f"  Nettokredit: '{row[5]}' -> {row[6]}")
            print()
        
    except Exception as e:
        print(f"✗ Error creating view: {e}")
        return False
    finally:
        conn.close()
    
    return True

if __name__ == "__main__":
    create_chart_view()
