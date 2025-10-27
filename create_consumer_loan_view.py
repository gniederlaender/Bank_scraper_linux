#!/usr/bin/env python3
"""
Create a database view with cleaned numeric data for consumer loan charting
Similar to create_housing_loan_view.py but for consumer loans
"""

import sqlite3
import os
from pathlib import Path

# Try to load dotenv if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not available, will use environment variables

# Get database path from environment or use relative path
DB_PATH = Path(os.getenv('CONSUMER_LOAN_DB_PATH', 'austrian_banks.db'))


def create_consumer_loan_chart_view(db_path: Path = None):
    """Create a view with cleaned numeric data for charting consumer loan data"""
    
    if db_path is None:
        db_path = DB_PATH
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    print("Creating consumer loan chart-ready view...")
    
    # Drop view if it exists
    cursor.execute("DROP VIEW IF EXISTS consumer_loan_chart_ready")
    
    # Create the view with cleaned numeric data
    create_view_sql = """
    CREATE VIEW consumer_loan_chart_ready AS
    SELECT 
        v.id,
        v.date_scraped,
        v.bank_name,
        v.product_name,
        
        -- Extract numeric Zinssatz from strings like "3.65% p.a." or "3,65%"
        CAST(
            REPLACE(
                REPLACE(
                    REPLACE(
                        TRIM(substr(v.rate, 1, 
                            CASE 
                                WHEN instr(v.rate, '%') > 0 THEN instr(v.rate, '%') - 1
                                ELSE length(v.rate)
                            END
                        )),
                        ',', '.'
                    ),
                    ' ', ''
                ),
                '\u00a0', ''  -- Remove non-breaking spaces
            ) AS REAL
        ) as rate_numeric,
        
        -- Extract numeric Effektiver Jahreszins from strings like "4.30%" or "4,30%"
        CAST(
            REPLACE(
                REPLACE(
                    REPLACE(
                        TRIM(substr(v.effektiver_jahreszins, 1, 
                            CASE 
                                WHEN instr(v.effektiver_jahreszins, '%') > 0 THEN instr(v.effektiver_jahreszins, '%') - 1
                                ELSE length(v.effektiver_jahreszins)
                            END
                        )),
                        ',', '.'
                    ),
                    ' ', ''
                ),
                '\u00a0', ''
            ) AS REAL
        ) as effektiver_jahreszins_numeric,
        
        -- Extract numeric monatliche_rate (monthly rate) from strings like "250,00 EUR" or "250.00"
        CAST(
            REPLACE(
                REPLACE(
                    TRIM(substr(v.monatliche_rate, 1, 
                        CASE 
                            WHEN instr(v.monatliche_rate, 'EUR') > 0 THEN instr(v.monatliche_rate, 'EUR') - 1
                            WHEN instr(v.monatliche_rate, 'Euro') > 0 THEN instr(v.monatliche_rate, 'Euro') - 1
                            ELSE length(v.monatliche_rate)
                        END
                    )),
                    '.', ''
                ),
                ',', '.'
            ) AS REAL
        ) as monatliche_rate_numeric,
        
        -- Keep original text fields
        v.rate,
        v.effektiver_jahreszins,
        v.monatliche_rate,
        v.nettokreditbetrag,
        v.gesamtbetrag,
        v.vertragslaufzeit,
        v.min_betrag,
        v.max_betrag,
        v.min_laufzeit,
        v.max_laufzeit,
        v.source_url,
        v.currency
        
    FROM interest_rates v
    WHERE v.rate != '-' AND v.effektiver_jahreszins != '-'
    """
    
    try:
        cursor.execute(create_view_sql)
        conn.commit()
        print("[OK] View 'consumer_loan_chart_ready' created successfully!")
        
        # Test the view with a sample query
        cursor.execute("SELECT COUNT(*) FROM consumer_loan_chart_ready")
        count = cursor.fetchone()[0]
        print(f"[OK] View contains {count} records")
        
        # Show sample of cleaned data
        cursor.execute("""
            SELECT 
                bank_name,
                date_scraped,
                rate, 
                rate_numeric, 
                effektiver_jahreszins, 
                effektiver_jahreszins_numeric,
                monatliche_rate,
                monatliche_rate_numeric
            FROM consumer_loan_chart_ready 
            ORDER BY date_scraped DESC, bank_name
            LIMIT 6
        """)
        
        print("\nSample cleaned data:")
        print("-" * 120)
        print(f"{'Bank':<20} | {'Date':<12} | {'Rate':<20} | {'Numeric':<8} | {'Eff. Zins':<15} | {'Numeric':<8}")
        print("-" * 120)
        for row in cursor.fetchall():
            print(f"{row[0]:<20} | {row[1]} | {row[2]:<20} | {row[3]:>8.3f} | {row[4]:<15} | {row[5]:>8.3f}")
        print("-" * 120)
        
    except Exception as e:
        print(f"[ERROR] Error creating view: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        conn.close()
    
    return True


if __name__ == "__main__":
    success = create_consumer_loan_chart_view()
    if success:
        print("\n[SUCCESS] View creation completed successfully!")
        print(f"   Database: {DB_PATH}")
        print("   You can now generate charts using this view.")
    else:
        print("\n[FAILED] View creation failed!")

