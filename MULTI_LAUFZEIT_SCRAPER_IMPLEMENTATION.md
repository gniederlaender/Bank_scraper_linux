# ✅ Multi-Laufzeit Scraper Implementation

## Overview

The durchblicker.at scraper has been enhanced to automatically scrape **multiple loan durations (Laufzeiten)** in a single run, with appropriate Fixierung variations for each.

## 🎯 What Changed

### Before (Single Laufzeit)
- Hardcoded to 30 Jahre Laufzeit
- Scraped fixed Fixierung values: [0, 5, 10, 15, 20, 25]
- Single database run per execution

### After (Multi-Laufzeit)
- **Loops through multiple Laufzeiten**: 15, 20, 25, 30 Jahre
- **Dynamic Fixierung calculation**: Respects constraint (Fixierung ≤ Laufzeit)
- **Multiple database runs**: One run per Laufzeit
- **Automatic recovery**: Continues if one Laufzeit fails

## 📊 New Scraping Sequence

For each scraping session, the scraper now:

```
For each Laufzeit (15, 20, 25, 30 Jahre):
  ├─ Navigate to Screen 1 (set Laufzeit)
  ├─ Navigate to Screen 2 (set Kaufpreis, etc.)
  ├─ Navigate to Screen 3 (set Haushalt data)
  ├─ Navigate to Screen 4 (results page)
  │   └─ For each Fixierung (0, 5, 10, ... ≤ Laufzeit):
  │       ├─ Set slider to Fixierung value
  │       ├─ Scrape financial data
  │       ├─ Take screenshot
  │       └─ Store variation data
  ├─ Save run to database
  └─ Navigate back to start for next Laufzeit
```

## 🔧 Key Functions Added/Modified

### 1. `get_fixierung_values_for_laufzeit(laufzeit_jahre: int) -> List[int]`

**Purpose**: Determine valid Fixierung values based on Laufzeit

**Logic**:
- Starts at 0 (variable rate)
- Then 5, 10, 15, 20... in 5-year increments
- Stops when reaching Laufzeit (constraint: Fixierung ≤ Laufzeit)

**Examples**:
```python
get_fixierung_values_for_laufzeit(15)  # Returns [0, 5, 10, 15]
get_fixierung_values_for_laufzeit(20)  # Returns [0, 5, 10, 15, 20]
get_fixierung_values_for_laufzeit(30)  # Returns [0, 5, 10, 15, 20, 25, 30]
get_fixierung_values_for_laufzeit(35)  # Returns [0, 5, 10, 15, 20, 25, 30, 35]
```

### 2. `screen1(page, laufzeit_jahre: int = 30) -> None`

**Changes**: 
- Now accepts `laufzeit_jahre` parameter (default 30 for backward compatibility)
- Sets the Laufzeit field to the specified value
- Supports dynamic Laufzeit configuration

### 3. `screen4(page, laufzeit_jahre: int = 30) -> List[Dict[str, Any]]`

**Changes**:
- Now accepts `laufzeit_jahre` parameter
- Dynamically calculates `slider_values` using `get_fixierung_values_for_laufzeit()`
- Adapts number of variations to Laufzeit

### 4. `run(playwright: Playwright) -> int`

**Complete rewrite** to support multi-Laufzeit scraping:

**New Features**:
- Loops through `laufzeiten_to_scrape = [15, 20, 25, 30]`
- Creates separate metadata for each Laufzeit
- Saves each Laufzeit as a separate database run
- Tracks success rate and total variations
- Automatic error recovery (continues if one Laufzeit fails)
- Navigation back to start between Laufzeiten

## 📋 Current Configuration

### Laufzeiten to Scrape
```python
laufzeiten_to_scrape = [15, 20, 25, 30]  # Can be expanded to [5, 10, 15, ..., 35]
```

### Expected Results per Run

| Laufzeit | Fixierung Options | Variations |
|----------|-------------------|------------|
| 15 Jahre | 0, 5, 10, 15 | 4 |
| 20 Jahre | 0, 5, 10, 15, 20 | 5 |
| 25 Jahre | 0, 5, 10, 15, 20, 25 | 6 |
| 30 Jahre | 0, 5, 10, 15, 20, 25, 30 | 7 |

**Total per session**: 4 runs, 22 variations

### To Expand to Full Range (5-35 Jahre)

Simply change line 745 in `test_durchblicker.py`:
```python
laufzeiten_to_scrape = [5, 10, 15, 20, 25, 30, 35]
```

This would create:
- **7 runs** with **42 total variations**

## 🛡️ Error Handling

### Per-Laufzeit Error Recovery
- If one Laufzeit fails, the scraper continues with the next
- Navigates back to start page for recovery
- Tracks successful vs failed runs
- Final summary shows success rate

### Database Safety
- Each Laufzeit saved as separate run
- If database save fails, scraping continues
- Errors logged but don't stop the entire session

## 📸 Screenshots

Screenshots are now tagged with both Laufzeit and Fixierung:
```
screen4_fixierung_0jahre_laufzeit_15.png
screen4_fixierung_5jahre_laufzeit_15.png
...
screen4_fixierung_0jahre_laufzeit_30.png
```

## 🗄️ Database Structure

Each scraping session now creates **multiple runs**:

```sql
scraping_runs:
  - Run 1: laufzeit_jahre = 15, variations: 4
  - Run 2: laufzeit_jahre = 20, variations: 5
  - Run 3: laufzeit_jahre = 25, variations: 6
  - Run 4: laufzeit_jahre = 30, variations: 7
```

## 🚀 Usage

### Standard Run (15-30 Jahre)
```bash
cd /opt/Bankcomparison
source venv/bin/activate
python3 test_durchblicker.py
```

### Full Workflow (Scrape + Generate HTML)
```bash
cd /opt/Bankcomparison
source venv/bin/activate
./run_full_scraper.sh
```

## ⏱️ Estimated Time

### Per Laufzeit
- Screen 1-3 navigation: ~10 seconds
- Screen 4 (per Fixierung): ~3 seconds each
- Database save: ~1 second
- Navigation back: ~3 seconds

**Total per Laufzeit**: ~30-60 seconds depending on variations

### Full Session (4 Laufzeiten)
- **Estimated**: 2-4 minutes
- **Depends on**: Network speed, server response, number of Fixierungen

### Full Range (5-35 Jahre, 7 Laufzeiten)
- **Estimated**: 4-7 minutes

## 📊 Output Example

```
================================================================================
[INFO] Starting scraping for Laufzeit: 15 Jahre
================================================================================

[INFO] Screen 1 start (Laufzeit: 15 Jahre)
[INFO] Laufzeit set to 15 via #laufzeit input
[INFO] Screen 1 done
...
[INFO] Fixierung values for 15 Jahre Laufzeit: [0, 5, 10, 15]
[INFO] Testing Fixierung slider at 0 years...
...
[INFO] ✅ Data saved to database! Run ID: 26
[INFO]    - Laufzeit: 15 Jahre
[INFO]    - Variations saved: 4

[INFO] Navigating back to start for next Laufzeit...

================================================================================
[INFO] Starting scraping for Laufzeit: 20 Jahre
================================================================================
...

================================================================================
[INFO] Multi-Laufzeit Scraping Complete!
================================================================================
[INFO] Successful runs: 4/4
[INFO] Total variations captured: 22
================================================================================
```

## 🎨 HTML Visualization

The generated HTML report (`generate_housing_loan_html.py`) is already ready:
- ✅ Laufzeit dropdown filter
- ✅ Zinssatz type toggle buttons
- ✅ Dynamic tables that match chart filter
- ✅ Combined AND filter logic
- ✅ Interactive legend with full labeling

## 🔮 Future Enhancements

### Easy Expansions

1. **Full Range (5-35 Jahre)**:
   ```python
   laufzeiten_to_scrape = list(range(5, 36, 5))  # [5, 10, 15, 20, 25, 30, 35]
   ```

2. **Custom Range via CLI**:
   ```python
   import argparse
   parser.add_argument('--laufzeit-min', type=int, default=15)
   parser.add_argument('--laufzeit-max', type=int, default=30)
   parser.add_argument('--laufzeit-step', type=int, default=5)
   ```

3. **Parallel Scraping**:
   - Run multiple browsers simultaneously
   - One Laufzeit per browser instance
   - Could reduce total time by 75%

4. **Smart Retry**:
   - Retry failed Laufzeiten
   - Configurable retry count
   - Save failed runs for manual review

## ⚠️ Important Notes

### Constraint Enforcement
The scraper **automatically enforces** the constraint:
> Fixierung ≤ Laufzeit

This means:
- 15 Jahre Laufzeit → max 15 Jahre Fixierung
- 30 Jahre Laufzeit → max 30 Jahre Fixierung
- No manual adjustment needed!

### Website Considerations
- Durchblicker.at may rate-limit requests
- Current implementation has delays (1-2 seconds) between actions
- Full navigation (Screen 1→4) between Laufzeiten ensures clean state

### Testing Recommendation
- **First run**: Use current range [15, 20, 25, 30] to verify
- **After success**: Expand to [5, 10, 15, 20, 25, 30, 35]
- **Monitor**: Check for any rate limiting or errors

## ✅ Validation

- ✅ Logic tested with test script
- ✅ Fixierung constraint validated
- ✅ No linting errors
- ✅ Backward compatible (default parameters)
- ✅ Database structure unchanged
- ✅ HTML generator ready for multi-Laufzeit data

## 📁 Files Modified

| File | Changes | Status |
|------|---------|--------|
| `test_durchblicker.py` | Added multi-Laufzeit loop | ✅ Complete |
| `generate_housing_loan_html.py` | Already handles multiple Laufzeiten | ✅ Ready |
| `db_helper.py` | No changes needed | ✅ Compatible |

## 📁 Files Created

| File | Purpose |
|------|---------|
| `test_multi_laufzeit_logic.py` | Test script for validation |
| `MULTI_LAUFZEIT_SCRAPER_IMPLEMENTATION.md` | This documentation |

## 🎯 Ready to Run!

The scraper is now ready to scrape multiple Laufzeiten in a single execution. Simply run:

```bash
cd /opt/Bankcomparison
source venv/bin/activate
python3 test_durchblicker.py
```

And it will automatically scrape 15, 20, 25, and 30 Jahre Laufzeiten with their respective Fixierung variations!
