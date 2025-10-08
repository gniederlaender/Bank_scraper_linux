#!/usr/bin/env python3
"""
Create a database view with cleaned numeric data for housing loan charting
"""

import sqlite3

def create_housing_loan_chart_view():
    """Create a view with cleaned numeric data for charting housing loan variations"""
    
    conn = sqlite3.connect('/opt/Bankcomparison/austrian_banks_housing_loan.db')
    cursor = conn.cursor()
    
    print("Creating housing loan chart-ready view...")
    
    # Drop view if it exists
    cursor.execute("DROP VIEW IF EXISTS housing_loan_chart_ready")
    
    # Create the view with cleaned numeric data
    create_view_sql = """
    CREATE VIEW housing_loan_chart_ready AS
    SELECT 
        v.id,
        v.run_id,
        v.fixierung_jahre,
        v.scrape_timestamp,
        
        -- Extract numeric Zinssatz from strings like "3,020 % p.a. variabel (30 Jahre)"
        -- Strategy: Extract everything before the first '%' sign, clean and convert
        CAST(
            REPLACE(
                REPLACE(
                    REPLACE(
                        TRIM(substr(v.zinssatz, 1, 
                            CASE 
                                WHEN instr(v.zinssatz, '%') > 0 THEN instr(v.zinssatz, '%') - 1
                                ELSE length(v.zinssatz)
                            END
                        )),
                        ',', '.'
                    ),
                    ' ', ''
                ),
                '\u00a0', ''  -- Remove non-breaking spaces
            ) AS REAL
        ) as zinssatz_numeric,
        
        -- Extract numeric Effektiver Zinssatz from strings like "3,240 % p.a."
        CAST(
            REPLACE(
                REPLACE(
                    REPLACE(
                        TRIM(substr(v.effektiver_zinssatz, 1, 
                            CASE 
                                WHEN instr(v.effektiver_zinssatz, '%') > 0 THEN instr(v.effektiver_zinssatz, '%') - 1
                                ELSE length(v.effektiver_zinssatz)
                            END
                        )),
                        ',', '.'
                    ),
                    ' ', ''
                ),
                '\u00a0', ''
            ) AS REAL
        ) as effektiver_zinssatz_numeric,
        
        -- Keep original text fields
        v.rate,
        v.zinssatz,
        v.laufzeit,
        v.anschlusskondition,
        v.effektiver_zinssatz,
        v.auszahlungsbetrag,
        v.einberechnete_kosten,
        v.kreditbetrag,
        v.gesamtbetrag,
        v.besicherung,
        
        -- Include run metadata for filtering/grouping
        r.kreditbetrag as run_kreditbetrag,
        r.laufzeit_jahre as run_laufzeit_jahre,
        r.kaufpreis as run_kaufpreis,
        r.scrape_date as run_scrape_date
        
    FROM fixierung_variations v
    INNER JOIN scraping_runs r ON v.run_id = r.id
    WHERE v.zinssatz != '-' AND v.effektiver_zinssatz != '-'
    """
    
    try:
        cursor.execute(create_view_sql)
        conn.commit()
        print("✓ View 'housing_loan_chart_ready' created successfully!")
        
        # Test the view with a sample query
        cursor.execute("SELECT COUNT(*) FROM housing_loan_chart_ready")
        count = cursor.fetchone()[0]
        print(f"✓ View contains {count} records")
        
        # Show sample of cleaned data
        cursor.execute("""
            SELECT 
                run_id,
                fixierung_jahre, 
                zinssatz, 
                zinssatz_numeric, 
                effektiver_zinssatz, 
                effektiver_zinssatz_numeric,
                scrape_timestamp
            FROM housing_loan_chart_ready 
            ORDER BY scrape_timestamp DESC, fixierung_jahre
            LIMIT 6
        """)
        
        print("\nSample cleaned data:")
        print("-" * 100)
        print(f"{'Run':<4} | {'Jahre':<5} | {'Zinssatz':<40} | {'Numeric':<8} | {'Eff. Zins':<20} | {'Numeric':<8}")
        print("-" * 100)
        for row in cursor.fetchall():
            print(f"{row[0]:<4} | {row[1]:>3}J | {row[2]:<40} | {row[3]:>8.3f} | {row[4]:<20} | {row[5]:>8.3f}")
        print("-" * 100)
        
    except Exception as e:
        print(f"✗ Error creating view: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        conn.close()
    
    return True

if __name__ == "__main__":
    success = create_housing_loan_chart_view()
    if success:
        print("\n✅ View creation completed successfully!")
        print("   You can now generate charts using this view.")
    else:
        print("\n❌ View creation failed!")

