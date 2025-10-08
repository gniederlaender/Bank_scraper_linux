"""
Database helper module for storing durchblicker.at scraping results
"""

import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any


DB_PATH = Path("/opt/Bankcomparison/austrian_banks_housing_loan.db")


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


if __name__ == "__main__":
    # Test: Create database structure
    print("Creating database structure...")
    create_database()
    print_database_summary()

