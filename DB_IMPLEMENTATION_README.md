# Database Implementation for Durchblicker.at Scraper

## ✅ Completed: Mock Data & Database Structure

### Files Created

1. **`mock_test_data.py`** - Mock structured data from scraping
   - Represents the data format we'll eventually get from `test_durchblicker.py`
   - Contains `run_metadata` and `verzinsung_variations`
   - Two test datasets: 500k/30yr and 300k/25yr

2. **`db_helper.py`** - Database operations module
   - `create_database()` - Creates tables and indexes
   - `insert_scraping_run()` - Inserts run metadata
   - `insert_verzinsung_variation()` - Inserts variation data
   - `save_scraping_data()` - Complete import (metadata + variations)
   - `get_all_runs()` - Query all runs
   - `get_variations_for_run()` - Query variations for a run
   - `print_database_summary()` - Display DB stats

3. **`test_db_import.py`** - Test script
   - Imports mock data to database
   - Verifies database operations
   - Displays results in formatted output

### Database Structure

#### Table: `scraping_runs`
Stores input parameters for each scraping run:
```sql
- id (PRIMARY KEY)
- scrape_date (TIMESTAMP)
- kreditbetrag (DECIMAL)
- laufzeit_jahre (INTEGER)
- kaufpreis (DECIMAL)
- kaufnebenkosten (DECIMAL)
- eigenmittel (DECIMAL)
- haushalt_alter (INTEGER)
- haushalt_einkommen (DECIMAL)
- haushalt_nutzflaeche (INTEGER)
- haushalt_kreditraten (DECIMAL)
- notes (TEXT)
```

#### Table: `verzinsung_variations`
Stores results for each Verzinsung variation (one run = multiple variations):
```sql
- id (PRIMARY KEY)
- run_id (FOREIGN KEY → scraping_runs.id)
- verzinsung_percent (INTEGER)
- rate (DECIMAL)
- zinssatz (VARCHAR)
- laufzeit (VARCHAR)
- anschlusskondition (VARCHAR)
- effektiver_zinssatz (VARCHAR)
- auszahlungsbetrag (DECIMAL)
- einberechnete_kosten (DECIMAL)
- kreditbetrag (DECIMAL)
- gesamtbetrag (DECIMAL)
- besicherung (VARCHAR)
- scrape_timestamp (TIMESTAMP)
```

### Data Structure Format

```python
{
    "run_metadata": {
        "scrape_date": datetime,
        "kreditbetrag": 500000.00,
        "laufzeit_jahre": 30,
        "kaufpreis": 500000.00,
        "kaufnebenkosten": 50000.00,
        "eigenmittel": 150000.00,
        "haushalt_alter": 45,
        "haushalt_einkommen": 5200.00,
        "haushalt_nutzflaeche": 100,
        "haushalt_kreditraten": 300.00,
        "notes": "Test run..."
    },
    "verzinsung_variations": [
        {
            "verzinsung_percent": 0,
            "rate": 1948.00,
            "zinssatz": "3,020 % p.a. variabel (25 Jahre)",
            "laufzeit": "25 Jahre",
            "anschlusskondition": None,
            "effektiver_zinssatz": "3,240 % p.a.",
            "auszahlungsbetrag": 400130.00,
            "einberechnete_kosten": 6370.00,
            "kreditbetrag": 406500.00,
            "gesamtbetrag": 584334.00,
            "besicherung": "Pfandrecht"
        },
        # ... more variations
    ]
}
```

### Test Results

✅ **Successfully tested:**
- Database creation
- Data import (2 runs with 8 total variations)
- Data retrieval and querying
- Foreign key relationships
- Formatted output display

### Next Steps

**To integrate with `test_durchblicker.py`:**

1. **Modify `screen4()` to return data** instead of just printing:
   ```python
   def screen4(page) -> List[Dict]:
       variations = []
       for value in slider_values:
           set_verzinsung_slider(value)
           details = scrape_offer_details()
           variations.append({
               'verzinsung_percent': value,
               'rate': parse_rate(details.get('Rate')),
               'zinssatz': details.get('Zinssatz'),
               # ... etc
           })
       return variations
   ```

2. **Collect metadata from screens 1-3**:
   ```python
   metadata = {
       'kreditbetrag': 500000,
       'laufzeit_jahre': 30,
       'kaufpreis': 500000,
       # ... etc
   }
   ```

3. **Save to database**:
   ```python
   from db_helper import save_scraping_data
   
   data = {
       'run_metadata': metadata,
       'verzinsung_variations': variations
   }
   run_id = save_scraping_data(data)
   ```

### Usage Examples

**Import mock data:**
```bash
python3 test_db_import.py
```

**Query specific run:**
```bash
python3 test_db_import.py 1
```

**Database location:**
```
/opt/Bankcomparison/austrian_banks_housing_loan.db
```

---

## Summary

✅ Database structure: **COMPLETE**  
✅ Mock data: **COMPLETE**  
✅ Import/export functions: **COMPLETE**  
✅ Testing: **COMPLETE**  
⏳ Integration with scraper: **PENDING** (next step)

