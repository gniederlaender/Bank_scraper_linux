"""
Database helper module for storing durchblicker.at scraping results
"""

import sqlite3
import os
from pathlib import Path
from datetime import datetime
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
        SELECT anbieter, angebotsdatum, fixzinssatz, effektivzinssatz, laufzeit, fileName
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


if __name__ == "__main__":
    # Test: Create database structure
    print("Creating database structure...")
    create_database()
    print_database_summary()

