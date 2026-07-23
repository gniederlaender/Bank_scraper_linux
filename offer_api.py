#!/usr/bin/env python3
"""
Flask API Server for loan offer management.
Provides endpoints to create and retrieve loan offers.
"""

import os
import sqlite3
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify
from flask_cors import CORS

# Try to load dotenv if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Configuration
BASE_DIR = Path(os.getenv('BANKCOMPARISON_BASE_DIR', '/opt/Bankcomparison'))
DB_PATH = BASE_DIR / os.getenv('HOUSING_LOAN_DB_PATH', 'austrian_banks_housing_loan.db')
API_PORT = int(os.getenv('OFFER_API_PORT', 5001))
# Bind to loopback only: this API has no auth, so it must never be reachable
# directly from the internet. It's meant to sit behind an Apache/nginx
# reverse proxy (e.g. https://yourdomain/bankapi/ -> 127.0.0.1:5001), which
# is also the only setup where the web report's relative fetch('/bankapi/...')
# call resolves to it. Override only for local development.
API_HOST = os.getenv('OFFER_API_HOST', '127.0.0.1')
# Origin allowed to call this API via CORS (the domain the report is served
# from). Same-origin requests through the reverse proxy don't need CORS at
# all; this only matters if the report HTML is hosted on a different origin.
ALLOWED_ORIGIN = os.getenv('OFFER_API_ALLOWED_ORIGIN')

app = Flask(__name__)
app.url_map.strict_slashes = False  # Allow both /offers and /offers/
CORS(app, origins=[ALLOWED_ORIGIN] if ALLOWED_ORIGIN else [])


def ensure_loan_offers_table():
    """Ensure the loan_offers table has the required columns."""
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    # Check if table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='loan_offers'")
    table_exists = cursor.fetchone() is not None

    if not table_exists:
        # Create table with full schema matching existing structure
        cursor.execute("""
            CREATE TABLE loan_offers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fileName TEXT NOT NULL,
                anbieter TEXT,
                angebotsdatum TEXT,
                nominale TEXT,
                kreditbetrag TEXT,
                laufzeit TEXT,
                anzahlRaten TEXT,
                sollzins TEXT,
                fixzinssatz TEXT,
                fixzinssatzBis TEXT,
                gebuehren TEXT,
                monatsrate TEXT,
                gesamtbetrag TEXT,
                rawJson TEXT NOT NULL,
                processingTime INTEGER NOT NULL,
                confidence REAL NOT NULL,
                createdAt TEXT DEFAULT (datetime('now')),
                effektivzinssatz TEXT,
                fixzinssatz_in_jahren TEXT,
                auszahlungsbetrag TEXT,
                auszahlungsdatum TEXT,
                datum1Rate TEXT,
                ratenanzahl TEXT,
                kreditende TEXT,
                sondertilgungen TEXT,
                restwert TEXT,
                fixzinsperiode TEXT,
                sollzinssatz TEXT,
                bearbeitungsgebuehr TEXT,
                schaetzgebuehr TEXT,
                kontofuehrungsgebuehr TEXT,
                kreditpruefkosten TEXT,
                vermittlerentgelt TEXT,
                grundbucheintragungsgebuehr TEXT,
                grundbuchseingabegebuehr TEXT,
                grundbuchsauszug TEXT,
                grundbuchsgesuch TEXT,
                legalisierungsgebuehr TEXT,
                gesamtkosten TEXT
            )
        """)
        print(f"[INFO] Created loan_offers table in {DB_PATH}")
    else:
        print(f"[INFO] loan_offers table already exists in {DB_PATH}")

    conn.commit()
    conn.close()


@app.route('/api/offers', methods=['GET'])
def get_offers():
    """Retrieve all loan offers."""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, anbieter, angebotsdatum, fixzinssatz, effektivzinssatz,
                   laufzeit, fixzinssatz_in_jahren, fileName, createdAt as created_at
            FROM loan_offers
            ORDER BY angebotsdatum DESC
        """)

        rows = cursor.fetchall()
        offers = [dict(row) for row in rows]
        conn.close()

        return jsonify({
            'status': 'success',
            'count': len(offers),
            'offers': offers
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/offers', methods=['POST'])
def create_offer():
    """Create a new loan offer."""
    try:
        data = request.json

        # Validate required fields
        required_fields = ['anbieter', 'angebotsdatum']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({
                    'status': 'error',
                    'message': f'Feld "{field}" ist erforderlich'
                }), 400

        # Format percentage values (convert from decimal input to German format)
        fixzinssatz = data.get('fixzinssatz', '')
        effektivzinssatz = data.get('effektivzinssatz', '')

        # If numeric, convert to German format with % sign
        try:
            if fixzinssatz and not '%' in str(fixzinssatz):
                fixzinssatz = f"{float(fixzinssatz):.3f}%".replace('.', ',')
        except ValueError:
            pass

        try:
            if effektivzinssatz and not '%' in str(effektivzinssatz):
                effektivzinssatz = f"{float(effektivzinssatz):.3f}%".replace('.', ',')
        except ValueError:
            pass

        # Format laufzeit
        laufzeit = data.get('laufzeit', '')
        if laufzeit and 'Jahre' not in str(laufzeit):
            laufzeit = f"{laufzeit} Jahre"

        # Format fixzinssatz_in_jahren
        fixzinssatz_in_jahren = data.get('fixzinssatz_in_jahren', '')
        if fixzinssatz_in_jahren and 'Jahre' not in str(fixzinssatz_in_jahren):
            fixzinssatz_in_jahren = f"{fixzinssatz_in_jahren} Jahre"

        # Convert date format if needed (from YYYY-MM-DD to DD.MM.YYYY)
        angebotsdatum = data.get('angebotsdatum', '')
        if '-' in angebotsdatum:
            try:
                dt = datetime.strptime(angebotsdatum, '%Y-%m-%d')
                angebotsdatum = dt.strftime('%d.%m.%Y')
            except ValueError:
                pass

        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO loan_offers (
                fileName, anbieter, angebotsdatum, fixzinssatz, effektivzinssatz,
                laufzeit, fixzinssatz_in_jahren, rawJson, processingTime, confidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data.get('fileName', 'manual_entry'),
            data.get('anbieter'),
            angebotsdatum,
            fixzinssatz,
            effektivzinssatz,
            laufzeit,
            fixzinssatz_in_jahren,
            '{}',  # rawJson - empty JSON for manual entries
            0,     # processingTime - 0 for manual entries
            1.0    # confidence - 1.0 for manual entries
        ))

        new_id = cursor.lastrowid
        conn.commit()
        conn.close()

        print(f"[INFO] Created new loan offer with ID: {new_id}")

        return jsonify({
            'status': 'success',
            'id': new_id,
            'message': 'Angebot erfolgreich gespeichert'
        }), 201

    except Exception as e:
        print(f"[ERROR] Failed to create offer: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/offers/<int:offer_id>', methods=['DELETE'])
def delete_offer(offer_id):
    """Delete a loan offer by ID."""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()

        cursor.execute("DELETE FROM loan_offers WHERE id = ?", (offer_id,))

        if cursor.rowcount == 0:
            conn.close()
            return jsonify({
                'status': 'error',
                'message': f'Angebot mit ID {offer_id} nicht gefunden'
            }), 404

        conn.commit()
        conn.close()

        return jsonify({
            'status': 'success',
            'message': f'Angebot {offer_id} gelöscht'
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({
        'status': 'ok',
        'database': str(DB_PATH),
        'timestamp': datetime.now().isoformat()
    })


# Initialize database table on module load (for WSGI servers)
ensure_loan_offers_table()


if __name__ == '__main__':
    print(f"[INFO] Starting Offer API Server on {API_HOST}:{API_PORT}")
    print(f"[INFO] Database: {DB_PATH}")
    if not ALLOWED_ORIGIN:
        print("[WARN] OFFER_API_ALLOWED_ORIGIN not set - cross-origin requests are blocked. "
              "Same-origin requests via the reverse proxy still work.")

    # Run the server (loopback-only; expose it via a reverse proxy, see README)
    app.run(host=API_HOST, port=API_PORT, debug=False)
