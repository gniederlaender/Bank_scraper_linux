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

app = Flask(__name__)
CORS(app)  # Allow cross-origin requests for local development


def ensure_loan_offers_table():
    """Create the loan_offers table if it doesn't exist."""
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS loan_offers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            anbieter TEXT NOT NULL,
            angebotsdatum TEXT NOT NULL,
            fixzinssatz TEXT,
            effektivzinssatz TEXT,
            laufzeit TEXT,
            fixzinssatz_in_jahren TEXT,
            fileName TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()
    print(f"[INFO] loan_offers table ensured in {DB_PATH}")


@app.route('/api/offers', methods=['GET'])
def get_offers():
    """Retrieve all loan offers."""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, anbieter, angebotsdatum, fixzinssatz, effektivzinssatz,
                   laufzeit, fixzinssatz_in_jahren, fileName, created_at
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
                anbieter, angebotsdatum, fixzinssatz, effektivzinssatz,
                laufzeit, fixzinssatz_in_jahren, fileName
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            data.get('anbieter'),
            angebotsdatum,
            fixzinssatz,
            effektivzinssatz,
            laufzeit,
            fixzinssatz_in_jahren,
            data.get('fileName', 'manual_entry')
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


if __name__ == '__main__':
    print(f"[INFO] Starting Offer API Server on port {API_PORT}")
    print(f"[INFO] Database: {DB_PATH}")

    # Ensure table exists
    ensure_loan_offers_table()

    # Run the server
    app.run(host='0.0.0.0', port=API_PORT, debug=False)
