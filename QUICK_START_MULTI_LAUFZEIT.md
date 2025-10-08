# 🚀 Quick Start: Multi-Laufzeit Scraping

## What's New?

The scraper now automatically scrapes **4 different loan durations** in one run:
- 15 Jahre (4 Fixierung variations)
- 20 Jahre (5 Fixierung variations)  
- 25 Jahre (6 Fixierung variations)
- 30 Jahre (7 Fixierung variations)

**Total**: 4 runs, 22 variations per session (~2-4 minutes)

## 🏃 Run the Scraper

```bash
cd /opt/Bankcomparison
source venv/bin/activate
python3 test_durchblicker.py
```

## 📊 View Results

After scraping, generate the HTML report:

```bash
python3 generate_housing_loan_html.py
```

Then open in browser:
```
file:///opt/Bankcomparison/bank_comparison_housing_loan_durchblicker.html
```

## 🎛️ Using the Interactive Report

1. **Laufzeit Dropdown**: Select which loan duration to view
   - "Alle Laufzeiten" - Show all data
   - "15 Jahre", "20 Jahre", etc. - Filter to specific duration

2. **Zinssatz Buttons**: Choose which rates to display
   - "Beide" - Show both Zinssatz and Effektiver Zinssatz
   - "Nur Zinssatz" - Show only nominal rate
   - "Nur Eff. Zinssatz" - Show only effective rate

3. **Tables Update Automatically**: When you change Laufzeit, the tables below update to show matching data

## ⚙️ Configuration

### Change Laufzeit Range

Edit line 745 in `test_durchblicker.py`:

```python
# Current (recommended for testing)
laufzeiten_to_scrape = [15, 20, 25, 30]

# Full range (5-35 Jahre)
laufzeiten_to_scrape = [5, 10, 15, 20, 25, 30, 35]

# Custom range
laufzeiten_to_scrape = [20, 25, 30]  # Only these three
```

## 🧪 Test Without Scraping

Validate the logic first:
```bash
python3 test_multi_laufzeit_logic.py
```

## 📈 Expected Results

### Database After One Scraping Session

```
4 new runs with 22 variations:
  Run A: 15 Jahre Laufzeit → 4 variations
  Run B: 20 Jahre Laufzeit → 5 variations
  Run C: 25 Jahre Laufzeit → 6 variations
  Run D: 30 Jahre Laufzeit → 7 variations
```

### HTML Chart Legend

Each line shows:
- Fixierung duration (0J, 5J, 10J...)
- Laufzeit duration (15J, 20J, 25J, 30J)
- Rate type (ZinsS or EffZ)

Examples:
- `5J fix - 30J ZinsS` = 5 years fixed, 30 years total, Zinssatz
- `15J fix - 25J EffZ` = 15 years fixed, 25 years total, Effektiver Zinssatz

## ⏱️ Timing

| Action | Time |
|--------|------|
| Per Fixierung variation | ~3 seconds |
| Per Laufzeit (avg 5.5 variations) | ~30-60 seconds |
| Full session (4 Laufzeiten) | ~2-4 minutes |
| Full range (7 Laufzeiten) | ~4-7 minutes |

## 🔍 Monitoring

Watch the console output for:
- `[INFO] Starting scraping for Laufzeit: X Jahre` - New Laufzeit started
- `[INFO] Fixierung values for X Jahre Laufzeit: [...]` - Shows what will be scraped
- `[INFO] ✅ Data saved to database! Run ID: X` - Success confirmation
- `[ERROR]` messages - Any failures (scraping continues)

## ⚠️ Troubleshooting

### If a Laufzeit Fails
- Scraper continues with next Laufzeit
- Check console output for error messages
- Failed Laufzeit won't be in database (can re-run later)

### If All Fail
- Check internet connection
- Verify durchblicker.at is accessible
- Check if website structure changed

### Rate Limiting
If you get blocked:
- Increase delays in code (line 700, 813)
- Run with fewer Laufzeiten
- Wait before re-running

## 📝 Notes

- All Laufzeiten use **same base parameters** (€500k loan, etc.)
- Each Laufzeit gets its own **Run ID** in database
- **Fixierung constraint** enforced automatically
- **Screenshots** saved for each variation
- **Recovery logic** ensures maximum data collection

## 🎯 Next Steps After First Run

1. Check HTML report shows all 4 Laufzeiten
2. Verify data in database is correct
3. If successful, expand to full range (5-35 Jahre)
4. Set up automated weekly/monthly scraping
