"""
Import Erste Bank loan offers from Excel file into erste_bank_loan_offers table
"""

import pandas as pd
import sqlite3
import json
from datetime import datetime
from pathlib import Path

# Configuration
EXCEL_FILE = 'FACE Pricings 092025_EBOe.xlsx'
DB_PATH = 'austrian_banks_housing_loan.db'
TABLE_NAME = 'erste_bank_loan_offers'

def format_date(date_value):
    """Convert datetime to DD.MM.YYYY format"""
    if pd.isna(date_value):
        return None
    if isinstance(date_value, datetime):
        return date_value.strftime('%d.%m.%Y')
    if isinstance(date_value, str):
        try:
            dt = pd.to_datetime(date_value)
            return dt.strftime('%d.%m.%Y')
        except:
            return None
    return None

def format_percentage(value):
    """Convert float to percentage string with comma (e.g., 3.20 -> "3,20%")"""
    if pd.isna(value):
        return None
    try:
        return f"{value:.2f}".replace('.', ',') + '%'
    except:
        return None

def format_laufzeit(laufzeit_str):
    """Convert '34y' to '34 Jahre'"""
    if pd.isna(laufzeit_str) or not isinstance(laufzeit_str, str):
        return None
    # Remove 'y' and add 'Jahre'
    laufzeit_str = str(laufzeit_str).strip()
    if laufzeit_str.endswith('y'):
        years = laufzeit_str[:-1]
        return f"{years} Jahre"
    return laufzeit_str

def format_fixzinsperiode(zibi_str):
    """Extract years from 'FIX 10Y' format"""
    if pd.isna(zibi_str) or not isinstance(zibi_str, str):
        return None
    zibi_str = str(zibi_str).strip()
    # Extract number from "FIX 10Y" -> "10 Jahre"
    import re
    match = re.search(r'(\d+)', zibi_str)
    if match:
        years = match.group(1)
        return f"{years} Jahre"
    return zibi_str

def format_amount(value):
    """Format numeric amount as string"""
    if pd.isna(value):
        return None
    try:
        return str(int(value))
    except:
        return None

def import_excel_to_db():
    """Import Excel data into database"""
    
    print(f"Reading Excel file: {EXCEL_FILE}")
    df = pd.read_excel(EXCEL_FILE)
    print(f"Found {len(df)} rows in Excel file")
    
    # Connect to database
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get all column names from the table
    cursor.execute(f'PRAGMA table_info({TABLE_NAME})')
    table_columns = [col[1] for col in cursor.fetchall()]
    
    # Prepare data for insertion
    inserted_count = 0
    skipped_count = 0
    
    for idx, row in df.iterrows():
        try:
            # Create rawJson from the row data
            row_dict = row.to_dict()
            # Convert datetime objects to strings for JSON serialization
            for key, value in row_dict.items():
                if isinstance(value, (datetime, pd.Timestamp)):
                    row_dict[key] = value.isoformat() if pd.notna(value) else None
                elif pd.isna(value):
                    row_dict[key] = None
            raw_json = json.dumps(row_dict, default=str, ensure_ascii=False)
            
            # Map Excel columns to database columns
            data = {
                'fileName': EXCEL_FILE,
                'rawJson': raw_json,
                'processingTime': 0,  # Not applicable for Excel import
                'confidence': 1.0,  # Excel data is considered 100% accurate
                'anbieter': 'Erste Bank',
                'angebotsdatum': format_date(row.get('DAT_PRICING')),
                'kreditbetrag': format_amount(row.get('NUM_VOL')),
                'laufzeit': format_laufzeit(row.get('COD_LFZ')),
                'fixzinsperiode': format_fixzinsperiode(row.get('COD_ZIBI')),
                'fixzinssatz_in_jahren': format_fixzinsperiode(row.get('COD_ZIBI')),
                'fixzinssatz': format_percentage(row.get('NUM_KUNDENKOND')),
                'auszahlungsdatum': format_date(row.get('DAT_ABWICKLUNG')),
                'gesamtbetrag': format_amount(row.get('ERGEBNIS')),
                'createdAt': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                # Additional fields that might be useful
                'nominale': format_amount(row.get('NUM_VOL')),
                'sollzinssatz': format_percentage(row.get('NUM_GENEHMIGTEMARGE')),
            }
            
            # Build INSERT statement with all columns
            # Only include columns that exist in the table
            columns = [col for col in table_columns if col != 'id']  # Exclude auto-increment id
            values = [data.get(col, None) for col in columns]
            
            # Create placeholders
            placeholders = ','.join(['?' for _ in columns])
            column_names = ','.join(columns)
            
            # Insert into database
            cursor.execute(
                f'INSERT INTO {TABLE_NAME} ({column_names}) VALUES ({placeholders})',
                values
            )
            
            inserted_count += 1
            
            if (idx + 1) % 50 == 0:
                print(f"  Processed {idx + 1} rows...")
                
        except Exception as e:
            print(f"  Error processing row {idx + 1}: {e}")
            skipped_count += 1
            continue
    
    # Commit changes
    conn.commit()
    
    # Verify insertion
    cursor.execute(f'SELECT COUNT(*) FROM {TABLE_NAME}')
    total_count = cursor.fetchone()[0]
    
    conn.close()
    
    print(f"\nImport completed!")
    print(f"  Rows inserted: {inserted_count}")
    print(f"  Rows skipped: {skipped_count}")
    print(f"  Total rows in table: {total_count}")

if __name__ == '__main__':
    import_excel_to_db()

