# 🏠 Housing Loan Scraper - Usage Guide

## 🚀 Quick Start

### **1. Run the Scraper**
```bash
cd /opt/Bankcomparison
source venv/bin/activate
python3 test_durchblicker.py
```

**What happens:**
- ✅ Navigates loan comparison calculator
- ✅ Fills in all parameters (500k loan, 30 years, etc.)
- ✅ Scrapes data for 6 Fixierung variations (0, 5, 10, 15, 20, 25 years)
- ✅ **Automatically saves to database**
- ✅ Takes screenshots at each step
- ⏱️ Duration: ~2-3 minutes

---

### **2. Generate HTML Report**
```bash
# First time only: Create the database view
python3 create_housing_loan_view.py

# Generate HTML report (can run anytime)
python3 generate_housing_loan_html.py
```

**Output:**
- 📄 `bank_comparison_housing_loan_durchblicker.html`
- 📊 `housing_loan_chart.png`

**View in browser:**
```bash
firefox /opt/Bankcomparison/bank_comparison_housing_loan_durchblicker.html
# or
xdg-open /opt/Bankcomparison/bank_comparison_housing_loan_durchblicker.html
```

---

## 📊 Chart Explanation

### **Time Series Chart Features:**

**12 Lines Total:**
- Each Fixierung variation (0, 5, 10, 15, 20, 25 years) has **2 lines**:
  - **Solid line (━━━)**: Zinssatz
  - **Dashed line (┄┄┄)**: Effektiver Zinssatz
  - **Same color** for both lines in a pair

**Color Scheme:**
- 🔵 **Blue**: 0J Fixierung (variabel)
- 🟢 **Green**: 5J Fixierung (fix 5 Jahre + variabel 25 Jahre)
- 🟠 **Orange**: 10J Fixierung (fix 10 Jahre + variabel 20 Jahre)
- 🔴 **Red**: 15J Fixierung (fix 15 Jahre + variabel 15 Jahre)
- 🟣 **Purple**: 20J Fixierung (fix 20 Jahre + variabel 10 Jahre)
- 🟤 **Brown**: 25J Fixierung (fix 25 Jahre + variabel 5 Jahre)

**Purpose:**
- Shows how interest rates change over time
- Compare Zinssatz vs Effektiver Zinssatz
- Track trends across multiple scraping runs

---

## 🗄️ Database Queries

### **View Summary:**
```bash
python3 query_db.py summary
```

### **List All Runs:**
```bash
python3 query_db.py list
```

### **View Specific Run:**
```bash
python3 query_db.py detail --run-id 4
```

### **Compare Two Runs:**
```bash
python3 query_db.py compare --run-id 1 --run-id 4
```

---

## ⚙️ Current Parameters

The scraper uses these **hardcoded** values (can be modified in `test_durchblicker.py`):

### **Screen 1:**
- Kreditbetrag: **500,000 €**
- Laufzeit: **30 Jahre**

### **Screen 2:**
- Finanzierungsvorhaben: Kauf
- Suchphase: Recherche
- Art der Immobilie: Eigentumswohnung
- Immobilie in Bau: bestehende Immobilie
- Lage der Immobilie: Wien
- Nutzung: Eigennutzung
- Kaufpreis: **500,000 €**
- Kaufnebenkosten: **50,000 €**
- Eigenmittel: **150,000 €**

### **Screen 3:**
- Ihr Alter: 45
- Finanzierung mit zweiter Person: Nein
- Anzahl unterhaltspflichtiger Kinder: Keine
- Berufliche Situation: Angestellt
- Netto-Einkommen: **5,200 €/Monat**
- Wohnnutzfläche: 100 m²
- Kredit-/Leasingraten: 300 €
- Anzahl der KFZ: keine

---

## 📂 Database Schema

### **Table: scraping_runs**
Stores input parameters for each scraping session.

**Fields:**
- `kreditbetrag`, `laufzeit_jahre`
- `kaufpreis`, `kaufnebenkosten`, `eigenmittel`
- `haushalt_alter`, `haushalt_einkommen`, etc.

### **Table: fixierung_variations**
Stores results for each Fixierung variation (fixed interest period: 0, 5, 10, 15, 20, 25 years).

**Fields:**
- `fixierung_jahre` (0, 5, 10, 15, 20, 25)
- `rate` (monthly payment)
- `zinssatz`, `effektiver_zinssatz`
- `auszahlungsbetrag`, `einberechnete_kosten`
- `kreditbetrag`, `gesamtbetrag`
- `besicherung`, `laufzeit`, `anschlusskondition`

### **View: housing_loan_chart_ready**
Pre-processed data with numeric fields for charting.

**Additional numeric fields:**
- `zinssatz_numeric` (e.g., 3.020)
- `effektiver_zinssatz_numeric` (e.g., 3.218)

---

## 🔧 Maintenance

### **Re-create View (if schema changes):**
```bash
python3 create_housing_loan_view.py
```

### **Regenerate Chart (without scraping):**
```bash
python3 generate_housing_loan_html.py
```

### **Check Database:**
```bash
sqlite3 austrian_banks_housing_loan.db
.tables
.schema scraping_runs
.schema fixierung_variations
SELECT COUNT(*) FROM scraping_runs;
SELECT COUNT(*) FROM fixierung_variations;
.quit
```

---

## 📸 Screenshots

All screenshots saved to: `/opt/Bankcomparison/screenshots/`

**Files:**
- `screen1-TIMESTAMP.png` - Initial calculator screen
- `screen2-TIMESTAMP.png` - Project details
- `screen3-TIMESTAMP.png` - Household information
- `screen4_fixierung_0jahre-TIMESTAMP.png` - Results at 0 years
- `screen4_fixierung_5jahre-TIMESTAMP.png` - Results at 5 years
- ... (one per Fixierung variation)
- `screen4-TIMESTAMP.png` - Final screen

---

## 🎯 Success Criteria - All Met!

✅ **Scraping**: Multi-step form navigation working
✅ **Data Extraction**: All Finanzierungsdetails captured
✅ **Slider Control**: All 6 Fixierung variations tested (0-25 years)
✅ **Database Storage**: Automatic save after scraping
✅ **Chart Generation**: Time series with paired lines
✅ **HTML Report**: Beautiful responsive design
✅ **Query Tools**: Complete database access

---

## 📞 Support

**Files to check for debugging:**
- `scraper.log` - Selenium logs (if using old scraper)
- `last_run.log` - Latest Playwright scraper output
- Screenshots in `/screenshots/`

**Common Issues:**
- Chart not showing? → Run `create_housing_loan_view.py` first
- Database locked? → Close any open connections
- View outdated? → Re-run view creation script

---

**Last Updated**: October 7, 2025
**Status**: ✅ Production Ready

