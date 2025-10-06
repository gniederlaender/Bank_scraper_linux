#!/usr/bin/env python3
import sqlite3
import pandas as pd
import re
from collections import Counter

def analyze_database():
    """Analyze the austrian_banks.db database structure and data patterns"""
    
    # Connect to the database
    conn = sqlite3.connect('/opt/Bankcomparison/austrian_banks.db')
    
    print("=" * 80)
    print("AUSTRIAN BANKS DATABASE ANALYSIS")
    print("=" * 80)
    
    # Get table schema
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(interest_rates)")
    columns = cursor.fetchall()
    
    print("\n1. DATABASE SCHEMA:")
    print("-" * 40)
    for col in columns:
        print(f"{col[1]:<20} {col[2]:<10} {'NULL' if col[3] else 'NOT NULL'}")
    
    # Get sample data
    df = pd.read_sql_query("SELECT * FROM interest_rates ORDER BY date_scraped DESC LIMIT 10", conn)
    
    print(f"\n2. SAMPLE DATA (Latest 10 records):")
    print("-" * 40)
    print(f"Total records in database: {len(pd.read_sql_query('SELECT * FROM interest_rates', conn))}")
    print(f"Sample records:")
    for idx, row in df.iterrows():
        print(f"\nRecord {idx + 1} (Bank: {row['bank_name']}, Date: {row['date_scraped']}):")
        print(f"  Rate: {row['rate']}")
        print(f"  Effektiver Jahreszins: {row['effektiver_jahreszins']}")
        print(f"  Nettokreditbetrag: {row['nettokreditbetrag']}")
        print(f"  Vertragslaufzeit: {row['vertragslaufzeit']}")
        print(f"  Gesamtbetrag: {row['gesamtbetrag']}")
        print(f"  Monatliche Rate: {row['monatliche_rate']}")
    
    # Analyze numeric-looking fields
    numeric_fields = ['rate', 'nettokreditbetrag', 'gesamtbetrag', 'vertragslaufzeit', 
                     'effektiver_jahreszins', 'monatliche_rate', 'min_betrag', 'max_betrag', 
                     'min_laufzeit', 'max_laufzeit']
    
    print(f"\n3. NUMERIC FIELDS ANALYSIS:")
    print("-" * 40)
    
    for field in numeric_fields:
        if field in df.columns:
            print(f"\n{field.upper()}:")
            non_null_values = df[field].dropna()
            print(f"  Non-null values: {len(non_null_values)}/{len(df)}")
            
            if len(non_null_values) > 0:
                # Show unique patterns
                unique_values = non_null_values.unique()
                print(f"  Unique values: {len(unique_values)}")
                print(f"  Sample values: {list(unique_values[:5])}")
                
                # Analyze patterns
                patterns = []
                for val in unique_values:
                    if isinstance(val, str):
                        # Check for percentage signs
                        if '%' in val:
                            patterns.append('contains %')
                        # Check for Euro signs
                        elif '€' in val or 'Euro' in val:
                            patterns.append('contains €/Euro')
                        # Check for commas
                        elif ',' in val:
                            patterns.append('contains comma')
                        # Check for dots
                        elif '.' in val:
                            patterns.append('contains dot')
                        # Check for spaces
                        elif ' ' in val:
                            patterns.append('contains space')
                        # Check if it's just numbers
                        elif val.isdigit():
                            patterns.append('digits only')
                        else:
                            patterns.append('other format')
                
                pattern_counts = Counter(patterns)
                print(f"  Format patterns: {dict(pattern_counts)}")
    
    # Check for data quality issues
    print(f"\n4. DATA QUALITY ANALYSIS:")
    print("-" * 40)
    
    for field in numeric_fields:
        if field in df.columns:
            non_null_values = df[field].dropna()
            if len(non_null_values) > 0:
                # Check for empty strings
                empty_strings = (non_null_values == '').sum()
                # Check for 'None' strings
                none_strings = (non_null_values == 'None').sum()
                # Check for 'null' strings
                null_strings = (non_null_values == 'null').sum()
                
                print(f"{field}: {empty_strings} empty, {none_strings} 'None', {null_strings} 'null'")
    
    # Analyze by bank
    print(f"\n5. DATA BY BANK:")
    print("-" * 40)
    
    bank_data = df.groupby('bank_name').size()
    print("Records per bank:")
    for bank, count in bank_data.items():
        print(f"  {bank}: {count} records")
    
    # Show latest data for each bank
    print(f"\n6. LATEST DATA BY BANK:")
    print("-" * 40)
    
    latest_by_bank = df.groupby('bank_name').first()
    for bank, row in latest_by_bank.iterrows():
        print(f"\n{bank.upper()} (Latest: {row['date_scraped']}):")
        print(f"  Rate: {row['rate']}")
        print(f"  Effektiver Jahreszins: {row['effektiver_jahreszins']}")
        print(f"  Nettokreditbetrag: {row['nettokreditbetrag']}")
        print(f"  Vertragslaufzeit: {row['vertragslaufzeit']}")
        print(f"  Gesamtbetrag: {row['gesamtbetrag']}")
        print(f"  Monatliche Rate: {row['monatliche_rate']}")
    
    conn.close()
    print(f"\n" + "=" * 80)
    print("ANALYSIS COMPLETE")
    print("=" * 80)

if __name__ == "__main__":
    analyze_database()
