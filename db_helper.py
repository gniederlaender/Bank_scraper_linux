"""
Database helper module for storing durchblicker.at scraping results
"""

import sqlite3
import os
import json
from collections import defaultdict
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

# Try to load dotenv if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not available, will use environment variables

# Get database path from environment or use relative path
DB_PATH = Path(os.getenv('HOUSING_LOAN_DB_PATH', 'austrian_banks_housing_loan.db'))


def create_database(db_path: Path = DB_PATH) -> None:
    """
    Create the database and tables if they don't exist
    
    Tables:
    - scraping_runs: Stores run metadata (input parameters)
    - fixierung_variations: Stores results for each Fixierung variation (fixed interest period in years)
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create scraping_runs table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scraping_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scrape_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            kreditbetrag DECIMAL(12,2),
            laufzeit_jahre INTEGER,
            kaufpreis DECIMAL(12,2),
            kaufnebenkosten DECIMAL(12,2),
            eigenmittel DECIMAL(12,2),
            haushalt_alter INTEGER,
            haushalt_einkommen DECIMAL(10,2),
            haushalt_nutzflaeche INTEGER,
            haushalt_kreditraten DECIMAL(10,2),
            notes TEXT
        )
    """)
    
    # Create fixierung_variations table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fixierung_variations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER,
            fixierung_jahre INTEGER,
            rate DECIMAL(10,2),
            zinssatz VARCHAR(100),
            laufzeit VARCHAR(50),
            anschlusskondition VARCHAR(100),
            effektiver_zinssatz VARCHAR(50),
            auszahlungsbetrag DECIMAL(12,2),
            einberechnete_kosten DECIMAL(12,2),
            kreditbetrag DECIMAL(12,2),
            gesamtbetrag DECIMAL(12,2),
            besicherung VARCHAR(100),
            scrape_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (run_id) REFERENCES scraping_runs(id)
        )
    """)
    
    # Create indexes for faster queries
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_run_date 
        ON scraping_runs(scrape_date)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_fixierung_run 
        ON fixierung_variations(run_id)
    """)
    
    conn.commit()
    conn.close()
    
    print(f"[INFO] Database created/verified at: {db_path}")


def insert_scraping_run(metadata: Dict[str, Any], db_path: Path = DB_PATH) -> int:
    """
    Insert a scraping run and return the run_id
    
    Args:
        metadata: Dictionary with run metadata (kreditbetrag, laufzeit_jahre, etc.)
        db_path: Path to database file
    
    Returns:
        run_id: ID of the inserted run
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO scraping_runs (
            scrape_date,
            kreditbetrag,
            laufzeit_jahre,
            kaufpreis,
            kaufnebenkosten,
            eigenmittel,
            haushalt_alter,
            haushalt_einkommen,
            haushalt_nutzflaeche,
            haushalt_kreditraten,
            notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        metadata.get('scrape_date', datetime.now()),
        metadata.get('kreditbetrag'),
        metadata.get('laufzeit_jahre'),
        metadata.get('kaufpreis'),
        metadata.get('kaufnebenkosten'),
        metadata.get('eigenmittel'),
        metadata.get('haushalt_alter'),
        metadata.get('haushalt_einkommen'),
        metadata.get('haushalt_nutzflaeche'),
        metadata.get('haushalt_kreditraten'),
        metadata.get('notes', '')
    ))
    
    run_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    print(f"[INFO] Inserted scraping run with ID: {run_id}")
    return run_id


def insert_fixierung_variation(
    run_id: int, 
    variation_data: Dict[str, Any], 
    db_path: Path = DB_PATH
) -> int:
    """
    Insert a Fixierung variation result (fixed interest period in years)
    
    Args:
        run_id: ID of the parent scraping run
        variation_data: Dictionary with variation data
        db_path: Path to database file
    
    Returns:
        variation_id: ID of the inserted variation
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO fixierung_variations (
            run_id,
            fixierung_jahre,
            rate,
            zinssatz,
            laufzeit,
            anschlusskondition,
            effektiver_zinssatz,
            auszahlungsbetrag,
            einberechnete_kosten,
            kreditbetrag,
            gesamtbetrag,
            besicherung,
            scrape_timestamp
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        run_id,
        variation_data.get('fixierung_jahre'),
        variation_data.get('rate'),
        variation_data.get('zinssatz'),
        variation_data.get('laufzeit'),
        variation_data.get('anschlusskondition'),
        variation_data.get('effektiver_zinssatz'),
        variation_data.get('auszahlungsbetrag'),
        variation_data.get('einberechnete_kosten'),
        variation_data.get('kreditbetrag'),
        variation_data.get('gesamtbetrag'),
        variation_data.get('besicherung'),
        datetime.now()
    ))
    
    variation_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return variation_id


def save_scraping_data(data: Dict[str, Any], db_path: Path = DB_PATH) -> int:
    """
    Save complete scraping data (metadata + all variations) to database
    
    Args:
        data: Dictionary with 'run_metadata' and 'fixierung_variations' keys
        db_path: Path to database file
    
    Returns:
        run_id: ID of the inserted run
    """
    # Ensure database exists
    create_database(db_path)
    
    # Insert run metadata
    run_id = insert_scraping_run(data['run_metadata'], db_path)
    
    # Insert all variations
    variations_count = 0
    for variation in data['fixierung_variations']:
        insert_fixierung_variation(run_id, variation, db_path)
        variations_count += 1
    
    print(f"[INFO] Saved run {run_id} with {variations_count} variations")
    return run_id


def get_all_runs(db_path: Path = DB_PATH) -> List[Dict[str, Any]]:
    """
    Retrieve all scraping runs
    
    Returns:
        List of dictionaries containing run data
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # Enable column access by name
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT * FROM scraping_runs 
        ORDER BY scrape_date DESC
    """)
    
    runs = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return runs


def get_variations_for_run(run_id: int, db_path: Path = DB_PATH) -> List[Dict[str, Any]]:
    """
    Retrieve all Fixierung variations for a specific run (fixed interest period in years)
    
    Args:
        run_id: ID of the scraping run
    
    Returns:
        List of dictionaries containing variation data
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT * FROM fixierung_variations 
        WHERE run_id = ?
        ORDER BY fixierung_jahre
    """, (run_id,))
    
    variations = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return variations


def print_database_summary(db_path: Path = DB_PATH) -> None:
    """Print a summary of database contents"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Count runs
    cursor.execute("SELECT COUNT(*) FROM scraping_runs")
    runs_count = cursor.fetchone()[0]
    
    # Count variations
    cursor.execute("SELECT COUNT(*) FROM fixierung_variations")
    variations_count = cursor.fetchone()[0]
    
    # Get latest run
    cursor.execute("""
        SELECT id, scrape_date, kreditbetrag, laufzeit_jahre 
        FROM scraping_runs 
        ORDER BY scrape_date DESC 
        LIMIT 1
    """)
    latest_run = cursor.fetchone()
    
    conn.close()
    
    print("\n" + "="*60)
    print("DATABASE SUMMARY")
    print("="*60)
    print(f"Total scraping runs: {runs_count}")
    print(f"Total variations: {variations_count}")
    
    if latest_run:
        print(f"\nLatest run:")
        print(f"  ID: {latest_run[0]}")
        print(f"  Date: {latest_run[1]}")
        print(f"  Kreditbetrag: €{latest_run[2]:,.0f}")
        print(f"  Laufzeit: {latest_run[3]} Jahre")
    
    print("="*60 + "\n")


def get_all_loan_offers(db_path: Path = DB_PATH) -> List[Dict[str, Any]]:
    """
    Retrieve all user loan offers from loan_offers table and parse German formats.
    
    Converts:
    - angebotsdatum: "DD.MM.YYYY" → datetime
    - fixzinssatz: "2,650%" → 2.65
    - effektivzinssatz: "3,30%" → 3.30
    
    Returns:
        List of dictionaries with parsed data:
        {
            'anbieter': str,
            'angebotsdatum': datetime,
            'fixzinssatz': float,
            'effektivzinssatz': float,
            'laufzeit': str,
            'fileName': str
        }
    """
    import re
    
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Query all loan offers
    cursor.execute("""
        SELECT anbieter, angebotsdatum, fixzinssatz, effektivzinssatz, laufzeit, fileName, fixzinssatz_in_jahren
        FROM loan_offers
        WHERE angebotsdatum IS NOT NULL 
          AND fixzinssatz IS NOT NULL 
          AND effektivzinssatz IS NOT NULL
        ORDER BY angebotsdatum DESC
    """)
    
    rows = cursor.fetchall()
    
    offers = []
    for row in rows:
        offer_dict = dict(row)
        
        # Parse date: "DD.MM.YYYY" → datetime
        try:
            date_str = offer_dict['angebotsdatum']
            parsed_date = datetime.strptime(date_str, '%d.%m.%Y')
            offer_dict['angebotsdatum'] = parsed_date
        except (ValueError, TypeError) as e:
            print(f"[WARN] Could not parse date '{offer_dict['angebotsdatum']}': {e}")
            continue
        
        # Parse fixzinssatz: "2,650%" → 2.65 (handle "2,950% p.a." format)
        try:
            fix_str = offer_dict['fixzinssatz']
            # Remove % sign and 'p.a.' text, replace comma with dot
            fix_str = fix_str.replace('%', '').replace('p.a.', '').replace(',', '.').strip()
            offer_dict['fixzinssatz'] = float(fix_str)
        except (ValueError, AttributeError) as e:
            print(f"[WARN] Could not parse fixzinssatz '{offer_dict['fixzinssatz']}': {e}")
            continue
        
        # Parse effektivzinssatz: "3,30%" → 3.30 (handle "p.a." format)
        try:
            eff_str = offer_dict.get('effektivzinssatz', '')
            # Remove % sign and 'p.a.' text, replace comma with dot
            eff_str = eff_str.replace('%', '').replace('p.a.', '').replace(',', '.').strip()
            offer_dict['effektivzinssatz'] = float(eff_str) if eff_str else None
        except (ValueError, AttributeError) as e:
            print(f"[WARN] Could not parse effektivzinssatz '{offer_dict.get('effektivzinssatz')}': {e}")
            continue
        
        # Parse laufzeit: "30 Jahre" → 30 (extract numeric value)
        try:
            laufzeit_str = offer_dict.get('laufzeit', '')
            if laufzeit_str:
                # Extract number from string like "30 Jahre" or "25 Jahre"
                import re
                match = re.search(r'(\d+)', laufzeit_str)
                if match:
                    offer_dict['laufzeit_numeric'] = int(match.group(1))
                else:
                    offer_dict['laufzeit_numeric'] = None
            else:
                offer_dict['laufzeit_numeric'] = None
        except (ValueError, AttributeError) as e:
            print(f"[WARN] Could not parse laufzeit '{offer_dict.get('laufzeit')}': {e}")
            offer_dict['laufzeit_numeric'] = None
        
        # Parse fixzinssatz_in_jahren: e.g. "10 Jahre" → 10.0
        fix_jahre_raw = offer_dict.get('fixzinssatz_in_jahren')
        fix_jahre_numeric = None
        if fix_jahre_raw not in (None, ''):
            try:
                if isinstance(fix_jahre_raw, (int, float)):
                    fix_jahre_numeric = float(fix_jahre_raw)
                else:
                    import re
                    match = re.search(r'(\d+[.,]?\d*)', str(fix_jahre_raw))
                    if match:
                        fix_jahre_numeric = float(match.group(1).replace(',', '.'))
            except (ValueError, TypeError):
                fix_jahre_numeric = None
        offer_dict['fixzinssatz_in_jahren_numeric'] = fix_jahre_numeric
        offer_dict['fixzinssatz_in_jahren_display'] = (
            f"{fix_jahre_numeric:g} Jahre" if fix_jahre_numeric is not None else "n/a"
        )

        offers.append(offer_dict)
    
    conn.close()
    
    print(f"[INFO] Retrieved {len(offers)} user loan offers from database")
    return offers


def get_loan_offers_by_anbieter(db_path: Path = DB_PATH) -> Dict[str, List[Dict[str, Any]]]:
    """
    Get all loan offers grouped by anbieter (bank/provider).
    
    Returns:
        Dictionary mapping anbieter → list of offers
    """
    offers = get_all_loan_offers(db_path)
    
    by_anbieter = {}
    for offer in offers:
        anbieter = offer.get('anbieter', 'Unknown')
        if anbieter not in by_anbieter:
            by_anbieter[anbieter] = []
        by_anbieter[anbieter].append(offer)
    
    return by_anbieter


# ============================================================================
# CONSUMER LOAN FUNCTIONS
# ============================================================================

CONSUMER_DB_PATH = Path(os.getenv('CONSUMER_LOAN_DB_PATH', 'austrian_banks.db'))


def create_consumer_loan_database(db_path: Path = CONSUMER_DB_PATH) -> None:
    """
    Create the consumer loan database with interest_rates table
    This matches the schema used by austrian_bankscraper_linux.py
    """
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS interest_rates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bank_name TEXT,
            product_name TEXT,
            rate TEXT,
            currency TEXT,
            date_scraped TIMESTAMP,
            source_url TEXT,
            nettokreditbetrag TEXT,
            gesamtbetrag TEXT,
            vertragslaufzeit TEXT,
            effektiver_jahreszins TEXT,
            monatliche_rate TEXT,
            min_betrag TEXT,
            max_betrag TEXT,
            min_laufzeit TEXT,
            max_laufzeit TEXT,
            full_text TEXT
        )
    """)
    
    # Create index for faster queries
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_scrape_date 
        ON interest_rates(date_scraped)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_bank_name 
        ON interest_rates(bank_name)
    """)
    
    conn.commit()
    conn.close()
    
    print(f"[INFO] Consumer loan database created/verified at: {db_path}")


def get_consumer_loan_runs(db_path: Path = CONSUMER_DB_PATH) -> List[Dict[str, Any]]:
    """
    Retrieve all consumer loan scraping runs
    Returns list of dictionaries with all interest_rates entries
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT * FROM interest_rates 
        ORDER BY date_scraped DESC
    """)
    
    runs = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return runs


def parse_german_number(value: str) -> Optional[float]:
    """
    Parse German number format to float
    Handles: "2,650%" → 2.65, "1.234,56" → 1234.56
    """
    if not value or value == "-":
        return None
    
    try:
        # Remove % sign and 'p.a.' text, replace comma with dot
        value = value.replace('%', '').replace('p.a.', '').replace(',', '.').strip()
        # Remove any remaining dots (thousand separators)
        value = value.replace('.', '', value.count('.') - 1) if value.count('.') > 1 else value
        return float(value)
    except (ValueError, AttributeError):
        return None


def parse_german_date(date_str: str) -> Optional[datetime]:
    """
    Parse German date format to datetime
    Handles: "DD.MM.YYYY" → datetime
    """
    if not date_str:
        return None
    
    try:
        return datetime.strptime(date_str, '%d.%m.%Y')
    except ValueError:
        try:
            return datetime.fromisoformat(date_str)
        except ValueError:
            return None


# ============================================================================
# JSON EXPORT FUNCTIONS FOR LLM COMMENTARY
# ============================================================================

def export_housing_loan_data_json(db_path: Path = DB_PATH) -> str:
    """
    Export housing loan time series data as JSON for LLM analysis.
    Groups data by Fixierung/Laufzeit combinations with aggregated statistics.
    Includes competitor loan offers from clients.
    
    Returns:
        JSON string with aggregated data organized by Fixierung/Laufzeit
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Check if view exists
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='view' AND name='housing_loan_chart_ready'
    """)
    view_exists = cursor.fetchone()
    
    if not view_exists:
        conn.close()
        raise ValueError("View 'housing_loan_chart_ready' does not exist. Please run create_housing_loan_view.py first.")
    
    # Query all data from the view, ordered by timestamp
    cursor.execute("""
        SELECT 
            run_id,
            run_scrape_date as scrape_timestamp,
            fixierung_jahre,
            run_laufzeit_jahre as laufzeit_jahre,
            zinssatz_numeric,
            effektiver_zinssatz_numeric,
            zinssatz,
            effektiver_zinssatz,
            run_kreditbetrag
        FROM housing_loan_chart_ready
        ORDER BY run_scrape_date ASC, fixierung_jahre, run_laufzeit_jahre
    """)
    
    rows = cursor.fetchall()
    
    # Convert to list of dictionaries
    raw_data = []
    for row in rows:
        # Convert datetime to ISO format string for JSON serialization
        timestamp = row['scrape_timestamp']
        if isinstance(timestamp, str):
            try:
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                timestamp = dt.isoformat()
            except:
                pass
        elif timestamp:
            timestamp = timestamp.isoformat() if hasattr(timestamp, 'isoformat') else str(timestamp)
        
        raw_data.append({
            'run_id': row['run_id'],
            'scrape_timestamp': timestamp,
            'fixierung_jahre': row['fixierung_jahre'],
            'laufzeit_jahre': row['laufzeit_jahre'],
            'zinssatz_numeric': row['zinssatz_numeric'],
            'effektiver_zinssatz_numeric': row['effektiver_zinssatz_numeric'],
            'zinssatz': row['zinssatz'],
            'effektiver_zinssatz': row['effektiver_zinssatz'],
            'kreditbetrag': float(row['run_kreditbetrag']) if row['run_kreditbetrag'] else None
        })
    
    # Group by Fixierung/Laufzeit combination with time series per group
    grouped_data = defaultdict(list)
    
    for record in raw_data:
        key = (record['fixierung_jahre'], record['laufzeit_jahre'])
        grouped_data[key].append(record)
    
    # Create aggregated time series by Fixierung/Laufzeit
    time_series_by_combo = {}
    for (fixierung, laufzeit), records in grouped_data.items():
        # Sort by timestamp
        sorted_records = sorted(records, key=lambda x: x['scrape_timestamp'])
        
        # Extract time series
        timestamps = [r['scrape_timestamp'] for r in sorted_records]
        zinssatz_series = [r['zinssatz_numeric'] for r in sorted_records]
        effektiver_series = [r['effektiver_zinssatz_numeric'] for r in sorted_records]
        
        # Calculate statistics for this combination
        zinssatz_values = [v for v in zinssatz_series if v is not None]
        effektiver_values = [v for v in effektiver_series if v is not None]
        
        # Get latest record
        latest_record = sorted_records[-1] if sorted_records else None
        
        # Calculate week-over-week changes by comparing with PREVIOUS scraping run
        # Group records by run_id to identify distinct scraping runs
        # This ensures we compare the actual latest run to the previous run, not just dates
        records_by_run_id = {}
        for r in sorted_records:
            run_id = r.get('run_id')
            if run_id is not None:
                # Keep the latest record for each run_id (in case of duplicates)
                if run_id not in records_by_run_id:
                    records_by_run_id[run_id] = r
                else:
                    # If multiple records for same run_id, keep the one with latest timestamp
                    existing_ts = records_by_run_id[run_id]['scrape_timestamp']
                    current_ts = r['scrape_timestamp']
                    try:
                        if isinstance(existing_ts, str):
                            existing_dt = datetime.fromisoformat(existing_ts.replace('Z', '+00:00'))
                        else:
                            existing_dt = existing_ts
                        if isinstance(current_ts, str):
                            current_dt = datetime.fromisoformat(current_ts.replace('Z', '+00:00'))
                        else:
                            current_dt = current_ts
                        if current_dt > existing_dt:
                            records_by_run_id[run_id] = r
                    except:
                        # If timestamp comparison fails, keep the existing one
                        pass
        
        # Get unique run_ids sorted by their scrape_timestamp
        def get_run_timestamp(run_id):
            r = records_by_run_id[run_id]
            ts = r.get('scrape_timestamp')
            if ts:
                try:
                    if isinstance(ts, str):
                        return datetime.fromisoformat(ts.replace('Z', '+00:00'))
                    else:
                        return ts
                except:
                    return datetime.min
            return datetime.min
        
        unique_run_ids = sorted(records_by_run_id.keys(), key=get_run_timestamp)
        
        # Calculate changes: compare latest with previous scraping run
        zinssatz_change_week = None
        effektiver_change_week = None
        if latest_record and len(unique_run_ids) >= 2:
            # Latest scraping run_id
            latest_run_id = unique_run_ids[-1]
            # Previous scraping run_id
            previous_run_id = unique_run_ids[-2]
            
            latest_record_for_run = records_by_run_id[latest_run_id]
            previous_record_for_run = records_by_run_id[previous_run_id]
            
            # Calculate changes (round to 3 decimal places to avoid floating point precision issues)
            if (latest_record_for_run.get('zinssatz_numeric') is not None and 
                previous_record_for_run.get('zinssatz_numeric') is not None):
                zinssatz_change_week = round(
                    latest_record_for_run['zinssatz_numeric'] - previous_record_for_run['zinssatz_numeric'],
                    3
                )
            
            if (latest_record_for_run.get('effektiver_zinssatz_numeric') is not None and 
                previous_record_for_run.get('effektiver_zinssatz_numeric') is not None):
                effektiver_change_week = round(
                    latest_record_for_run['effektiver_zinssatz_numeric'] - previous_record_for_run['effektiver_zinssatz_numeric'],
                    3
                )
        
        time_series_by_combo[f"fixierung_{fixierung}_laufzeit_{laufzeit}"] = {
            'fixierung_jahre': fixierung,
            'laufzeit_jahre': laufzeit,
            'total_data_points': len(records),
            'date_range': {
                'earliest': sorted_records[0]['scrape_timestamp'] if sorted_records else None,
                'latest': sorted_records[-1]['scrape_timestamp'] if sorted_records else None
            },
            'statistics': {
                'zinssatz': {
                    'min': min(zinssatz_values) if zinssatz_values else None,
                    'max': max(zinssatz_values) if zinssatz_values else None,
                    'latest': latest_record['zinssatz_numeric'] if latest_record else None,
                    'change_week': zinssatz_change_week
                },
                'effektiver_zinssatz': {
                    'min': min(effektiver_values) if effektiver_values else None,
                    'max': max(effektiver_values) if effektiver_values else None,
                    'latest': latest_record['effektiver_zinssatz_numeric'] if latest_record else None,
                    'change_week': effektiver_change_week
                }
            },
            'time_series': {
                'timestamps': timestamps,
                'zinssatz_values': zinssatz_series,
                'effektiver_zinssatz_values': effektiver_series
            }
        }
    
    # Get competitor loan offers
    loan_offers_list = get_all_loan_offers(db_path)
    competitor_offers = []
    for offer in loan_offers_list:
        # Convert datetime to ISO string if needed
        offer_date = offer.get('angebotsdatum')
        if hasattr(offer_date, 'isoformat'):
            offer_date = offer_date.isoformat()
        elif isinstance(offer_date, str):
            try:
                dt = datetime.strptime(offer_date, '%d.%m.%Y')
                offer_date = dt.isoformat()
            except:
                pass
        
        competitor_offers.append({
            'anbieter': offer.get('anbieter'),
            'angebotsdatum': offer_date,
            'fixzinssatz': offer.get('fixzinssatz'),
            'effektivzinssatz': offer.get('effektivzinssatz'),
            'laufzeit': offer.get('laufzeit'),
            'laufzeit_numeric': offer.get('laufzeit_numeric'),
            'fixzinssatz_in_jahren_numeric': offer.get('fixzinssatz_in_jahren_numeric')
        })
    
    # Sort competitor offers by date (newest first)
    # Handle both ISO format strings and datetime objects
    def get_sort_date(offer):
        date_str = offer.get('angebotsdatum', '')
        if not date_str:
            return datetime.min
        try:
            if isinstance(date_str, str):
                if 'T' in date_str:
                    return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                else:
                    return datetime.strptime(date_str, '%Y-%m-%d')
            elif hasattr(date_str, 'isoformat'):
                return date_str
        except:
            return datetime.min
        return datetime.min
    
    competitor_offers.sort(key=get_sort_date, reverse=True)
    
    # Overall summary
    if raw_data:
        zinssatz_all = [d['zinssatz_numeric'] for d in raw_data if d['zinssatz_numeric'] is not None]
        effektiver_all = [d['effektiver_zinssatz_numeric'] for d in raw_data if d['effektiver_zinssatz_numeric'] is not None]
        
        summary = {
            'total_records': len(raw_data),
            'unique_combinations': len(time_series_by_combo),
            'date_range': {
                'earliest': raw_data[0]['scrape_timestamp'] if raw_data else None,
                'latest': raw_data[-1]['scrape_timestamp'] if raw_data else None
            },
            'overall_statistics': {
                'zinssatz': {
                    'min': min(zinssatz_all) if zinssatz_all else None,
                    'max': max(zinssatz_all) if zinssatz_all else None
                },
                'effektiver_zinssatz': {
                    'min': min(effektiver_all) if effektiver_all else None,
                    'max': max(effektiver_all) if effektiver_all else None
                }
            },
            'competitor_offers_count': len(competitor_offers)
        }
    else:
        summary = {
            'total_records': 0,
            'unique_combinations': 0,
            'date_range': {'earliest': None, 'latest': None},
            'overall_statistics': {
                'zinssatz': {'min': None, 'max': None},
                'effektiver_zinssatz': {'min': None, 'max': None}
            },
            'competitor_offers_count': len(competitor_offers)
        }
    
    result = {
        'metadata': {
            'export_date': datetime.now().isoformat(),
            'data_type': 'housing_loan',
            'database_path': str(db_path)
        },
        'summary': summary,
        'market_data_by_fixierung_laufzeit': time_series_by_combo,
        'competitor_offers': competitor_offers
    }
    
    conn.close()
    
    return json.dumps(result, indent=2, ensure_ascii=False)


def export_consumer_loan_data_json(db_path: Path = CONSUMER_DB_PATH) -> str:
    """
    Export all consumer loan time series data as JSON for LLM analysis.
    Exports full historical data from consumer_loan_chart_ready view or interest_rates table.
    
    Returns:
        JSON string with all time series data
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Check if view exists, otherwise use table directly
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='view' AND name='consumer_loan_chart_ready'
    """)
    view_exists = cursor.fetchone()
    
    if view_exists:
        # Use the view if it exists
        cursor.execute("""
            SELECT 
                id,
                date_scraped,
                bank_name,
                product_name,
                rate_numeric,
                effektiver_jahreszins_numeric,
                monatliche_rate_numeric,
                rate,
                effektiver_jahreszins,
                monatliche_rate,
                nettokreditbetrag,
                gesamtbetrag,
                vertragslaufzeit
            FROM consumer_loan_chart_ready
            ORDER BY date_scraped ASC, bank_name
        """)
    else:
        # Fallback to interest_rates table
        cursor.execute("""
            SELECT 
                id,
                date_scraped,
                bank_name,
                product_name,
                rate,
                effektiver_jahreszins,
                monatliche_rate,
                nettokreditbetrag,
                gesamtbetrag,
                vertragslaufzeit
            FROM interest_rates
            WHERE rate != '-' AND effektiver_jahreszins != '-'
            ORDER BY date_scraped ASC, bank_name
        """)
    
    rows = cursor.fetchall()
    
    # Convert to list of dictionaries
    data = []
    for row in rows:
        # Convert sqlite3.Row to dict for easier access
        row_dict = dict(row)
        
        # Convert datetime to ISO format string for JSON serialization
        timestamp = row_dict.get('date_scraped')
        if isinstance(timestamp, str):
            try:
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                timestamp = dt.isoformat()
            except Exception:
                pass
        elif timestamp:
            timestamp = timestamp.isoformat() if hasattr(timestamp, 'isoformat') else str(timestamp)
        
        record = {
            'id': row_dict.get('id'),
            'date_scraped': timestamp,
            'bank_name': row_dict.get('bank_name'),
            'product_name': row_dict.get('product_name'),
            'rate': row_dict.get('rate'),
            'effektiver_jahreszins': row_dict.get('effektiver_jahreszins'),
            'monatliche_rate': row_dict.get('monatliche_rate'),
            'nettokreditbetrag': row_dict.get('nettokreditbetrag'),
            'gesamtbetrag': row_dict.get('gesamtbetrag'),
            'vertragslaufzeit': row_dict.get('vertragslaufzeit')
        }
        
        # Add numeric fields if available (from view)
        if 'rate_numeric' in row_dict:
            record['rate_numeric'] = row_dict.get('rate_numeric')
            record['effektiver_jahreszins_numeric'] = row_dict.get('effektiver_jahreszins_numeric')
            record['monatliche_rate_numeric'] = row_dict.get('monatliche_rate_numeric')
        
        data.append(record)
    
    # Helper to get numeric effective rate with fallback from string
    def get_eff_value(rec: dict) -> Optional[float]:
        val = rec.get('effektiver_jahreszins_numeric')
        if val is not None:
            return val
        s = rec.get('effektiver_jahreszins')
        if not s:
            return None
        try:
            # Remove percent signs and spaces, convert German decimal to float
            s_clean = str(s).replace('%', '').replace('Euro', '').strip()
            s_clean = s_clean.replace('.', '').replace(',', '.')
            return float(s_clean)
        except Exception:
            return None
    
    # Create summary statistics
    if data:
        # Get numeric values if available
        rate_values = [d.get('rate_numeric') for d in data if d.get('rate_numeric') is not None]
        effektiver_values = [d.get('effektiver_jahreszins_numeric') for d in data if d.get('effektiver_jahreszins_numeric') is not None]
        
        # Get latest data point
        latest = data[-1] if data else None
        
        # Get unique banks
        banks = list(set(d['bank_name'] for d in data if d['bank_name']))
        
        # Get data from last week
        from datetime import timedelta
        week_ago = datetime.now() - timedelta(days=7)
        week_ago_data = [
            d for d in data 
            if d['date_scraped'] and 
            datetime.fromisoformat(d['date_scraped'].replace('Z', '+00:00')) >= week_ago
        ] if data else []
        
        summary = {
            'total_records': len(data),
            'unique_banks': len(banks),
            'banks': banks,
            'date_range': {
                'earliest': data[0]['date_scraped'] if data else None,
                'latest': data[-1]['date_scraped'] if data else None
            },
            'statistics': {
                'rate': {
                    'min': min(rate_values) if rate_values else None,
                    'max': max(rate_values) if rate_values else None,
                    'latest': latest.get('rate_numeric') if latest else None
                },
                'effektiver_jahreszins': {
                    'min': min(effektiver_values) if effektiver_values else None,
                    'max': max(effektiver_values) if effektiver_values else None,
                    'latest': latest.get('effektiver_jahreszins_numeric') if latest else None
                }
            },
            'records_last_week': len(week_ago_data)
        }
    else:
        summary = {
            'total_records': 0,
            'unique_banks': 0,
            'banks': [],
            'date_range': {'earliest': None, 'latest': None},
            'statistics': {
                'rate': {'min': None, 'max': None, 'latest': None},
                'effektiver_jahreszins': {'min': None, 'max': None, 'latest': None}
            },
            'records_last_week': 0
        }
    
    # Pre-compute per-bank latest vs previous effective rate changes (similar to housing loan logic)
    per_bank_changes = {}
    if data:
        # Group records by bank
        records_by_bank: Dict[str, List[dict]] = defaultdict(list)
        for rec in data:
            bank = rec.get('bank_name')
            ts = rec.get('date_scraped')
            if bank and ts:
                records_by_bank[bank].append(rec)
        
        for bank_name, records in records_by_bank.items():
            # Sort records by date_scraped
            def get_ts(rec: dict) -> datetime:
                ts = rec.get('date_scraped')
                if ts:
                    try:
                        return datetime.fromisoformat(str(ts).replace('Z', '+00:00'))
                    except Exception:
                        return datetime.min
                return datetime.min
            
            sorted_recs = sorted(records, key=get_ts)
            if len(sorted_recs) < 2:
                continue  # need at least two points per bank
            
            prev_rec = sorted_recs[-2]
            latest_rec = sorted_recs[-1]
            prev_val = get_eff_value(prev_rec)
            latest_val = get_eff_value(latest_rec)
            
            if prev_val is None or latest_val is None:
                continue
            
            delta = round(latest_val - prev_val, 4)
            delta_bps = int(round(delta * 100))
            
            per_bank_changes[bank_name] = {
                'bank_name': bank_name,
                'previous': {
                    'date_scraped': prev_rec.get('date_scraped'),
                    'effektiver_jahreszins': prev_val
                },
                'latest': {
                    'date_scraped': latest_rec.get('date_scraped'),
                    'effektiver_jahreszins': latest_val
                },
                'change': {
                    'delta': delta,
                    'delta_bps': delta_bps
                }
            }
    
    result = {
        'metadata': {
            'export_date': datetime.now().isoformat(),
            'data_type': 'consumer_loan',
            'database_path': str(db_path)
        },
        'summary': summary,
        'time_series_data': data,
        'per_bank_changes': per_bank_changes
    }
    
    conn.close()
    
    return json.dumps(result, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    # Test: Create database structure
    print("Creating database structure...")
    create_database()
    print_database_summary()

