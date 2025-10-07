"""
Mock test data from durchblicker.at scraping
This represents the structured data we'll eventually get from test_durchblicker.py
"""

from datetime import datetime

# Mock data structure based on actual scraping results
mock_scraping_data = {
    # Scraping run metadata
    "run_metadata": {
        "scrape_date": datetime.now(),
        "kreditbetrag": 500000.00,
        "laufzeit_jahre": 30,
        "kaufpreis": 500000.00,
        "kaufnebenkosten": 50000.00,
        "eigenmittel": 150000.00,
        "haushalt_alter": 45,
        "haushalt_einkommen": 5200.00,
        "haushalt_nutzflaeche": 100,
        "haushalt_kreditraten": 300.00,
        "notes": "Test run with 500k loan, 30 years"
    },
    
    # Verzinsung variations from Screen 4
    "verzinsung_variations": [
        {
            "verzinsung_percent": 0,
            "rate": 1948.00,
            "zinssatz": "3,020 % p.a. variabel (25 Jahre)",
            "laufzeit": "25 Jahre",
            "anschlusskondition": None,  # Not present for variabel
            "effektiver_zinssatz": "3,240 % p.a.",
            "auszahlungsbetrag": 400130.00,
            "einberechnete_kosten": 6370.00,
            "kreditbetrag": 406500.00,
            "gesamtbetrag": 584334.00,
            "besicherung": "Pfandrecht"
        },
        {
            "verzinsung_percent": 5,
            "rate": 1952.00,
            "zinssatz": "3,040 % p.a. fix (5 Jahre)",
            "laufzeit": "25 Jahre",
            "anschlusskondition": "3,020 % p.a. variabel (20 Jahre)",
            "effektiver_zinssatz": "3,260 % p.a.",
            "auszahlungsbetrag": 400130.00,
            "einberechnete_kosten": 6370.00,
            "kreditbetrag": 406500.00,
            "gesamtbetrag": 585626.00,
            "besicherung": "Pfandrecht"
        },
        {
            "verzinsung_percent": 10,
            "rate": 2009.00,
            "zinssatz": "3,300 % p.a. fix (10 Jahre)",
            "laufzeit": "25 Jahre",
            "anschlusskondition": "3,020 % p.a. variabel (15 Jahre)",
            "effektiver_zinssatz": "3,525 % p.a.",
            "auszahlungsbetrag": 400130.00,
            "einberechnete_kosten": 6370.00,
            "kreditbetrag": 406500.00,
            "gesamtbetrag": 602571.00,
            "besicherung": "Pfandrecht"
        },
        {
            "verzinsung_percent": 15,
            "rate": 2075.00,
            "zinssatz": "3,600 % p.a. fix (15 Jahre)",
            "laufzeit": "25 Jahre",
            "anschlusskondition": "3,020 % p.a. variabel (10 Jahre)",
            "effektiver_zinssatz": "3,831 % p.a.",
            "auszahlungsbetrag": 400130.00,
            "einberechnete_kosten": 6370.00,
            "kreditbetrag": 406500.00,
            "gesamtbetrag": 622462.00,
            "besicherung": "Pfandrecht"
        },
        {
            "verzinsung_percent": 20,
            "rate": 2086.00,
            "zinssatz": "3,650 % p.a. fix (20 Jahre)",
            "laufzeit": "25 Jahre",
            "anschlusskondition": "3,020 % p.a. variabel (5 Jahre)",
            "effektiver_zinssatz": "3,882 % p.a.",
            "auszahlungsbetrag": 400130.00,
            "einberechnete_kosten": 6370.00,
            "kreditbetrag": 406500.00,
            "gesamtbetrag": 625812.00,
            "besicherung": "Pfandrecht"
        },
        {
            "verzinsung_percent": 25,
            "rate": None,  # No data available for 25%
            "zinssatz": "-",
            "laufzeit": "-",
            "anschlusskondition": "-",
            "effektiver_zinssatz": "-",
            "auszahlungsbetrag": None,
            "einberechnete_kosten": None,
            "kreditbetrag": None,
            "gesamtbetrag": None,
            "besicherung": "-"
        }
    ]
}


# Alternative mock data with different parameters for testing
mock_scraping_data_2 = {
    "run_metadata": {
        "scrape_date": datetime.now(),
        "kreditbetrag": 300000.00,
        "laufzeit_jahre": 25,
        "kaufpreis": 300000.00,
        "kaufnebenkosten": 30000.00,
        "eigenmittel": 80000.00,
        "haushalt_alter": 45,
        "haushalt_einkommen": 5200.00,
        "haushalt_nutzflaeche": 100,
        "haushalt_kreditraten": 300.00,
        "notes": "Test run with 300k loan, 25 years"
    },
    "verzinsung_variations": [
        {
            "verzinsung_percent": 0,
            "rate": 1236.00,
            "zinssatz": "3,120 % p.a. variabel (25 Jahre)",
            "laufzeit": "25 Jahre",
            "anschlusskondition": None,
            "effektiver_zinssatz": "3,366 % p.a.",
            "auszahlungsbetrag": 250391.00,
            "einberechnete_kosten": 4109.00,
            "kreditbetrag": 254500.00,
            "gesamtbetrag": 370677.00,
            "besicherung": "Pfandrecht"
        },
        {
            "verzinsung_percent": 5,
            "rate": 1238.00,
            "zinssatz": "3,140 % p.a. fix (5 Jahre)",
            "laufzeit": "25 Jahre",
            "anschlusskondition": "3,120 % p.a. variabel (20 Jahre)",
            "effektiver_zinssatz": "3,386 % p.a.",
            "auszahlungsbetrag": 250391.00,
            "einberechnete_kosten": 4109.00,
            "kreditbetrag": 254500.00,
            "gesamtbetrag": 371491.00,
            "besicherung": "Pfandrecht"
        }
    ]
}


def get_mock_data(dataset: int = 1):
    """
    Get mock data for testing
    
    Args:
        dataset: 1 for 500k/30yr data, 2 for 300k/25yr data
    
    Returns:
        Dictionary with run_metadata and verzinsung_variations
    """
    if dataset == 1:
        return mock_scraping_data
    elif dataset == 2:
        return mock_scraping_data_2
    else:
        raise ValueError(f"Unknown dataset: {dataset}")


if __name__ == "__main__":
    # Test: print the mock data structure
    import json
    from datetime import datetime
    
    data = get_mock_data(1)
    
    # Custom JSON encoder for datetime
    class DateTimeEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            return super().default(obj)
    
    print("Mock Data Structure:")
    print(json.dumps(data, indent=2, cls=DateTimeEncoder))

