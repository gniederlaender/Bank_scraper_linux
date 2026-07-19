from __future__ import annotations

import sys
import os
import time
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

from playwright.sync_api import Playwright, sync_playwright, TimeoutError as PlaywrightTimeoutError
from db_helper import save_scraping_data

# Try to load dotenv if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Get screenshot directory from environment or use relative path
BASE_DIR = Path(os.getenv('BANKCOMPARISON_BASE_DIR', '.'))
SCREENSHOTS_DIR = Path(os.getenv('SCREENSHOTS_DIR', BASE_DIR / 'screenshots'))

# Enable screenshots for debugging (disabled to prevent crashes)
ENABLE_SCREENSHOTS = False


def ensure_dirs() -> None:
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)


def ts_filename(prefix: str) -> str:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{prefix}-{timestamp}.png"


def log_print(label: str, value: str) -> None:
    print(f"{label}: {value}".strip())


def save_screenshot(page, name: str) -> None:
    """Save a screenshot with timestamp if screenshots are enabled."""
    if ENABLE_SCREENSHOTS:
        filepath = SCREENSHOTS_DIR / ts_filename(name)
        page.screenshot(path=str(filepath), full_page=True)
        print(f"[DEBUG] Screenshot saved: {filepath}", flush=True)


def parse_currency_to_float(value: Optional[str]) -> Optional[float]:
    """Parse currency string to float."""
    if not value or value == "-":
        return None
    value = value.replace("€", "").replace(" ", "").strip()
    value = value.replace(".", "")
    value = value.replace(",", ".")
    try:
        return float(value)
    except (ValueError, AttributeError):
        return None


def get_fixierung_values_for_laufzeit(laufzeit_jahre: int) -> List[int]:
    """Determine the Fixierung slider values based on Laufzeit."""
    fixierung_values = []
    current = 0
    while current <= laufzeit_jahre:
        fixierung_values.append(current)
        if current == 0:
            current = 5
        else:
            current += 5
    return fixierung_values


def accept_cookies(page) -> None:
    """Accept cookies if banner appears."""
    time.sleep(2)  # Wait for banner to appear

    # Try clicking the accept button with various selectors
    cookie_selectors = [
        # Durchblicker specific
        'button:has-text("Alle akzeptieren")',
        'button:has-text("Akzeptieren")',
        '[class*="CookieBanner"] button:has-text("Akzeptieren")',
        '[class*="CookieBanner"] button',
        '[aria-label="Cookie-Banner"] button:has-text("Akzeptieren")',
        '[aria-label="Cookie-Banner"] button:has-text("Alle akzeptieren")',
        '[role="dialog"] button:has-text("Akzeptieren")',
        '[role="dialog"] button:has-text("Alle akzeptieren")',
        # Generic
        '#onetrust-accept-btn-handler',
        '[id*="accept"]',
        'button:has-text("Zustimmen")',
    ]

    for selector in cookie_selectors:
        try:
            btn = page.locator(selector).first
            if btn.count() > 0:
                btn.click(timeout=5000)
                print(f"[INFO] Cookie banner accepted via: {selector}", flush=True)
                time.sleep(2)
                return
        except Exception:
            continue

    # Last resort: try keyboard navigation
    try:
        page.keyboard.press("Tab")
        time.sleep(0.5)
        page.keyboard.press("Tab")
        time.sleep(0.5)
        page.keyboard.press("Enter")
        print("[INFO] Cookie banner accepted via keyboard", flush=True)
        time.sleep(2)
        return
    except Exception:
        pass

    print("[WARN] Could not accept cookie banner", flush=True)


def screen1(page, laufzeit_jahre: int = 35) -> None:
    """Screen 1: Set initial parameters."""
    page.goto("https://durchblicker.at/kreditrechner", wait_until="load")
    time.sleep(2)

    accept_cookies(page)
    save_screenshot(page, "screen1_initial")

    def clear_and_type(locator, value: str):
        locator.click()
        page.keyboard.press("Control+A")
        page.keyboard.press("Delete")
        locator.type(value, delay=20)

    # Set Kreditbetrag to 500000
    filled_amount = False
    for label in ["Kreditbetrag", "Kreditbetrag in Euro", "Kreditbetrag €"]:
        try:
            amount_el = page.get_by_label(label, exact=False)
            if amount_el.count() > 0:
                clear_and_type(amount_el.nth(0), "500000")
                filled_amount = True
                print(f"[INFO] Kreditbetrag set to 500000", flush=True)
                break
        except Exception:
            continue

    if not filled_amount:
        try:
            kb_section = page.locator("text=Kreditbetrag").first
            input_box = kb_section.locator("xpath=ancestor::section|ancestor::div").locator("input[type='number'], input").first
            clear_and_type(input_box, "500000")
            print(f"[INFO] Kreditbetrag set via fallback", flush=True)
        except Exception as e:
            print(f"[WARN] Could not set Kreditbetrag: {e}", flush=True)

    # Set Laufzeit
    try:
        laufzeit_input = page.locator("#laufzeit").first
        laufzeit_input.wait_for(state="visible", timeout=8000)
        laufzeit_input.click()
        page.keyboard.press("Control+A")
        page.keyboard.press("Delete")
        laufzeit_input.type(str(laufzeit_jahre), delay=50)
        laufzeit_input.blur()
        print(f"[INFO] Laufzeit set to {laufzeit_jahre}", flush=True)
    except Exception as e:
        print(f"[WARN] Could not set Laufzeit: {e}", flush=True)

    time.sleep(1)
    save_screenshot(page, "screen1_filled")

    # Click "Jetzt berechnen"
    for name in ["Jetzt berechnen", "Berechnen"]:
        try:
            page.get_by_role("button", name=name).first.click(timeout=5000)
            print(f"[INFO] Clicked '{name}' button", flush=True)
            break
        except Exception:
            continue


def screen2(page) -> None:
    """Screen 2: Project details."""
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass

    time.sleep(3)
    save_screenshot(page, "screen2_initial")

    print("[INFO] Screen 2 interactions start", flush=True)

    # Finanzierungsvorhaben
    try:
        sel = page.locator("#select_immokredit_projekt_vorhaben").first
        if sel.count() > 0:
            sel.select_option(value="kauf", timeout=6000)
            print("[INFO] Finanzierungsvorhaben set", flush=True)
    except Exception as e:
        print(f"[WARN] Finanzierungsvorhaben: {e}", flush=True)

    # Other dropdowns
    selectors_values = [
        ("#select_immokredit_projekt_suchphaseKauf", "recherche"),
        ("#select_immokredit_projekt_immobilie", "wohnung"),
        ("#select_immokredit_projekt_inBau", "fertig"),
        ("#select_immokredit_projekt_lage", "wien"),
        ("#select_immokredit_projekt_nutzung", "eigen"),
    ]

    for sel_id, val in selectors_values:
        try:
            page.locator(sel_id).first.select_option(value=val, timeout=4000)
        except Exception:
            pass

    def clear_type_and_blur(selector: str, value: str) -> None:
        try:
            el = page.locator(selector).first
            el.wait_for(state="visible", timeout=5000)
            el.click()
            page.keyboard.press("Control+A")
            page.keyboard.press("Delete")
            el.type(value, delay=20)
            el.blur()
        except Exception:
            pass

    # Input fields
    clear_type_and_blur("#input_immokredit_projektkosten_kaufpreis", "500000")
    clear_type_and_blur("#input_immokredit_projektkosten_kaufnebenkosten", "50000")
    clear_type_and_blur("#input_immokredit_projektkosten_eigenmittel", "150000")

    print("[INFO] Screen 2 interactions done", flush=True)
    time.sleep(0.5)
    save_screenshot(page, "screen2_filled")

    # Click Weiter
    for name in ["Weiter", "Nächster Schritt", "Fortfahren"]:
        try:
            page.get_by_role("button", name=name).first.click(timeout=6000)
            print(f"[INFO] Clicked '{name}'", flush=True)
            break
        except Exception:
            continue


def screen3(page) -> None:
    """Screen 3: Household details."""
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass

    time.sleep(3)
    save_screenshot(page, "screen3_initial")

    def clear_type_and_blur(selector: str, value: str) -> bool:
        try:
            el = page.locator(selector).first
            if el.count() == 0:
                return False
            el.wait_for(state="visible", timeout=6000)
            el.click()
            page.keyboard.press("Control+A")
            page.keyboard.press("Delete")
            el.type(value, delay=20)
            el.blur()
            return True
        except Exception:
            return False

    print("[INFO] Screen 3 fill start", flush=True)

    # Alter
    clear_type_and_blur("input[id*='haushalt'][id*='alter'], #input_immokredit_haushalt_alter", "45")

    # Zweite Person -> Nein
    try:
        page.get_by_role("radio", name=re.compile(r"nein", re.I)).first.check()
    except Exception:
        try:
            page.locator("label:has-text('Nein')").first.click()
        except Exception:
            pass

    # Kinder -> Keine
    try:
        page.locator("#select_immokredit_haushalt_kinder").first.select_option(label="Keine", timeout=4000)
    except Exception:
        pass

    # Berufliche Situation
    try:
        page.locator("#select_immokredit_haushalt_berufsituation").first.select_option(value="erwerb", timeout=4000)
    except Exception:
        pass

    # Netto-Einkommen
    try:
        einkommen_input = page.locator("#input_immokredit_haushalt_einkommen").first
        einkommen_input.wait_for(state="visible", timeout=8000)
        einkommen_input.click()
        time.sleep(0.3)
        page.keyboard.press("Control+A")
        page.keyboard.press("Delete")
        einkommen_input.type("8500", delay=50)
        einkommen_input.blur()
        print("[INFO] Netto-Einkommen set", flush=True)
    except Exception as e:
        print(f"[WARN] Netto-Einkommen: {e}", flush=True)

    # Wohnnutzfläche
    clear_type_and_blur("#input_immokredit_haushalt_nutzflaeche", "100")

    # Kredit-/Leasingraten
    clear_type_and_blur("input[id*='leasing'], input[id*='kredit'][id*='rate']", "300")

    # KFZ
    try:
        page.locator("#select_immokredit_haushalt_kfz").first.select_option(label="keine", timeout=4000)
    except Exception:
        pass

    print("[INFO] Screen 3 fill done", flush=True)
    time.sleep(0.5)
    save_screenshot(page, "screen3_filled")

    # Click Berechnen
    print("[INFO] Clicking Berechnen...", flush=True)
    for name in ["Berechnen", "Jetzt berechnen", "Angebote berechnen"]:
        try:
            page.get_by_role("button", name=name).first.click(timeout=5000)
            print(f"[INFO] Clicked '{name}'", flush=True)
            break
        except Exception:
            continue

    time.sleep(2)


def extract_financial_data_from_page(page) -> dict:
    """
    Extract financial data using multiple strategies.
    This is a more robust version that handles different page structures.
    """
    details = {}

    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass

    time.sleep(3)

    # Strategy 1: Look for data-sentry-component
    try:
        fin_div = page.locator('[data-sentry-component="Finanzierungsdetails"]').first
        if fin_div.count() > 0:
            text = fin_div.inner_text()
            print(f"[DEBUG] Found Finanzierungsdetails via sentry component", flush=True)
            details = parse_financial_text(text)
            if details:
                return details
    except Exception:
        pass

    # Strategy 2: Look for section/div containing "Finanzierungsdetails"
    try:
        for selector in [
            'section:has-text("Finanzierungsdetails")',
            'div:has-text("Finanzierungsdetails")',
        ]:
            try:
                elem = page.locator(selector).first
                if elem.count() > 0:
                    text = elem.inner_text()
                    if "Zinssatz" in text:
                        print(f"[DEBUG] Found via: {selector}", flush=True)
                        details = parse_financial_text(text)
                        if details:
                            return details
            except Exception:
                continue
    except Exception:
        pass

    # Strategy 3: Look for specific labels and extract nearby values
    try:
        labels_to_find = [
            ("Rate", "Rate"),
            ("Zinssatz", "Zinssatz"),
            ("Effektiver Zinssatz", "Effektiver Zinssatz"),
            ("Laufzeit", "Laufzeit"),
            ("Auszahlungsbetrag", "Auszahlungsbetrag"),
            ("Kreditbetrag", "Kreditbetrag"),
        ]

        for label_text, key in labels_to_find:
            try:
                # Find the label element
                label_el = page.locator(f"text={label_text}").first
                if label_el.count() > 0:
                    # Get parent and try to find value
                    parent = label_el.locator("xpath=../..")
                    spans = parent.locator("span")
                    for i in range(spans.count()):
                        span_text = spans.nth(i).inner_text().strip()
                        if span_text and span_text != label_text:
                            if "%" in span_text or "€" in span_text or span_text.replace(",", "").replace(".", "").isdigit():
                                details[key] = span_text
                                print(f"[DEBUG] Found {key}: {span_text}", flush=True)
                                break
            except Exception:
                continue
    except Exception:
        pass

    # Strategy 4: Extract all visible text and parse
    if not details:
        try:
            body_text = page.locator("body").inner_text()
            details = parse_financial_text(body_text)
        except Exception:
            pass

    # Strategy 5: Look for specific patterns in page HTML
    if not details:
        try:
            html = page.content()
            # Look for patterns like: Zinssatz</div><div>3,020 % p.a.
            patterns = [
                (r'Zinssatz[^<]*</[^>]+>[^<]*<[^>]+>([0-9,.]+ ?% ?p\.?a\.?[^<]*)', 'Zinssatz'),
                (r'Effektiver Zinssatz[^<]*</[^>]+>[^<]*<[^>]+>([0-9,.]+ ?% ?p\.?a\.?[^<]*)', 'Effektiver Zinssatz'),
                (r'Rate[^<]*</[^>]+>[^<]*<[^>]+>([€ 0-9,.]+)', 'Rate'),
                (r'Laufzeit[^<]*</[^>]+>[^<]*<[^>]+>([0-9]+ Jahre[^<]*)', 'Laufzeit'),
            ]
            for pattern, key in patterns:
                match = re.search(pattern, html, re.IGNORECASE)
                if match:
                    details[key] = match.group(1).strip()
                    print(f"[DEBUG] Found via regex {key}: {details[key]}", flush=True)
        except Exception:
            pass

    return details


def parse_financial_text(text: str) -> dict:
    """Parse financial data from text block."""
    details = {}
    lines = text.split('\n')

    # Look for key-value pairs
    key_patterns = {
        'Rate': r'Rate[:\s]*(€?\s*[0-9.,]+)',
        'Zinssatz': r'(?<!Effektiver )Zinssatz[:\s]*([0-9,.]+ ?%[^E\n]*)',
        'Effektiver Zinssatz': r'Effektiver Zinssatz[:\s]*([0-9,.]+ ?%[^\n]*)',
        'Laufzeit': r'Laufzeit[:\s]*([0-9]+ Jahre[^\n]*)',
        'Auszahlungsbetrag': r'Auszahlungsbetrag[:\s]*(€?\s*[0-9.,]+)',
        'Kreditbetrag': r'Kreditbetrag[:\s]*(€?\s*[0-9.,]+)',
        'Gesamtbetrag': r'(?:Zu zahlender )?Gesamtbetrag[:\s]*(€?\s*[0-9.,]+)',
        'Besicherung': r'Besicherung[:\s]*([^\n]+)',
        'Anschlusskondition': r'Anschlusskondition[:\s]*([^\n]+)',
    }

    for key, pattern in key_patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = match.group(1).strip()
            if value:
                details[key] = value

    return details


def screen4(page, laufzeiten_to_scrape: List[int] = None) -> Dict[int, List[Dict[str, Any]]]:
    """Screen 4: Results page with sliders."""
    if laufzeiten_to_scrape is None:
        laufzeiten_to_scrape = [35, 30, 25, 20, 15]

    try:
        page.wait_for_load_state("networkidle", timeout=30000)
    except Exception:
        pass

    # Wait for results
    for key in ["Kreditangebote", "Ergebnisse", "Angebote", "Finanzierungsdetails"]:
        try:
            page.locator(f"text={key}").first.wait_for(state="visible", timeout=8000)
            print(f"[INFO] Found '{key}' on results page", flush=True)
            break
        except Exception:
            continue

    time.sleep(3)
    save_screenshot(page, "screen4_initial")

    # Check if we're actually on the results page
    try:
        body_text = page.locator("body").inner_text()
        if "Finanzierungsdetails" not in body_text and "Zinssatz" not in body_text:
            print("[ERROR] Not on results page - might still be on form", flush=True)
            save_screenshot(page, "screen4_not_results")
            # Try to find and click submit button again
            for name in ["Berechnen", "Angebote anzeigen", "Ergebnisse"]:
                try:
                    page.get_by_role("button", name=name).first.click(timeout=3000)
                    time.sleep(5)
                    break
                except Exception:
                    continue
    except Exception:
        pass

    def set_slider(slider_id: str, value: int, name: str) -> bool:
        """Set a slider to a specific value."""
        try:
            slider = page.locator(f"#{slider_id}").first
            if slider.count() == 0:
                print(f"[WARN] Slider #{slider_id} not found", flush=True)
                return False

            slider.wait_for(state="visible", timeout=8000)
            slider.fill(str(value))
            slider.dispatch_event("change")
            slider.dispatch_event("input")
            time.sleep(2)
            print(f"[INFO] {name} slider set to {value}", flush=True)
            return True
        except Exception as e:
            print(f"[WARN] Error setting {name} slider: {e}", flush=True)
            return False

    all_data_by_laufzeit = {}

    for laufzeit in laufzeiten_to_scrape:
        print(f"\n{'='*70}")
        print(f"[INFO] Processing Laufzeit: {laufzeit} Jahre")
        print('='*70)

        if not set_slider("laufzeitslider", laufzeit, "Laufzeit"):
            # Try alternative slider IDs
            for alt_id in ["laufzeit", "laufzeit-slider", "duration-slider"]:
                if set_slider(alt_id, laufzeit, "Laufzeit"):
                    break

        fixierung_values = get_fixierung_values_for_laufzeit(laufzeit)
        print(f"[INFO] Fixierung values: {fixierung_values}", flush=True)

        variations_data = []

        for fixierung in fixierung_values:
            print(f"\n[INFO] Setting Fixierung to {fixierung} years...", flush=True)

            if not set_slider("fixverzinsungslider", fixierung, "Fixierung"):
                for alt_id in ["fixierung", "fix-slider", "fixed-rate-slider"]:
                    if set_slider(alt_id, fixierung, "Fixierung"):
                        break

            time.sleep(2)

            # Extract data
            print(f"[INFO] Extracting data for {laufzeit}J/{fixierung}J...", flush=True)
            details = extract_financial_data_from_page(page)

            if details:
                print(f"[INFO] Data extracted: {len(details)} fields", flush=True)
                for k, v in details.items():
                    print(f"    {k}: {v}", flush=True)
            else:
                print(f"[WARN] No data extracted!", flush=True)
                save_screenshot(page, f"screen4_nodata_{laufzeit}j_{fixierung}j")

            variation_data = {
                'fixierung_jahre': fixierung,
                'rate': parse_currency_to_float(details.get('Rate')),
                'zinssatz': details.get('Zinssatz', '-'),
                'laufzeit': details.get('Laufzeit', '-'),
                'anschlusskondition': details.get('Anschlusskondition'),
                'effektiver_zinssatz': details.get('Effektiver Zinssatz', '-'),
                'auszahlungsbetrag': parse_currency_to_float(details.get('Auszahlungsbetrag')),
                'einberechnete_kosten': parse_currency_to_float(details.get('Einberechnete Kosten')),
                'kreditbetrag': parse_currency_to_float(details.get('Kreditbetrag')),
                'gesamtbetrag': parse_currency_to_float(details.get('Gesamtbetrag')),
                'besicherung': details.get('Besicherung', '-')
            }
            variations_data.append(variation_data)

        all_data_by_laufzeit[laufzeit] = variations_data
        print(f"\n[INFO] ✓ Laufzeit {laufzeit} Jahre: {len(variations_data)} variations")

    save_screenshot(page, "screen4_final")
    return all_data_by_laufzeit


def run(playwright: Playwright) -> int:
    ensure_dirs()

    browser = playwright.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-setuid-sandbox",
            "--single-process",
            "--no-zygote"
        ]
    )
    context = browser.new_context(locale="de-DE")
    page = context.new_page()
    page.set_default_timeout(15000)

    laufzeiten_to_scrape = [35, 30, 25, 20, 15]
    max_laufzeit = max(laufzeiten_to_scrape)

    base_metadata = {
        'kreditbetrag': 500000.00,
        'kaufpreis': 500000.00,
        'kaufnebenkosten': 50000.00,
        'eigenmittel': 150000.00,
        'haushalt_alter': 45,
        'haushalt_einkommen': 8500.00,
        'haushalt_nutzflaeche': 100,
        'haushalt_kreditraten': 300.00,
    }

    try:
        print("\n" + "="*80)
        print(f"[INFO] Durchblicker Scraper V2 - Multi-Laufzeit Session")
        print(f"[INFO] Laufzeiten: {laufzeiten_to_scrape}")
        print("="*80 + "\n")

        print(f"[INFO] Screen 1 start (Laufzeit: {max_laufzeit})", flush=True)
        screen1(page, laufzeit_jahre=max_laufzeit)
        print("[INFO] Screen 1 done", flush=True)

        print("[INFO] Screen 2 start", flush=True)
        screen2(page)
        print("[INFO] Screen 2 done", flush=True)

        print("[INFO] Screen 3 start", flush=True)
        screen3(page)
        print("[INFO] Screen 3 done", flush=True)

        print("[INFO] Screen 4 start", flush=True)
        all_data_by_laufzeit = screen4(page, laufzeiten_to_scrape=laufzeiten_to_scrape)
        print("[INFO] Screen 4 done", flush=True)

        # Save to database
        print("\n" + "="*80)
        print("[INFO] Saving data to database...")
        print("="*80)

        successful_runs = 0
        total_variations = 0
        has_valid_data = False

        for laufzeit, variations_data in all_data_by_laufzeit.items():
            # Check if any variation has actual data
            for v in variations_data:
                if v.get('zinssatz') and v.get('zinssatz') != '-':
                    has_valid_data = True
                    break

            run_metadata = base_metadata.copy()
            run_metadata['scrape_date'] = datetime.now()
            run_metadata['laufzeit_jahre'] = laufzeit
            run_metadata['notes'] = f'V2 scraper - {laufzeit} Jahre'

            scraping_data = {
                'run_metadata': run_metadata,
                'fixierung_variations': variations_data
            }

            try:
                run_id = save_scraping_data(scraping_data)
                print(f"[INFO] ✅ Run ID {run_id}: {laufzeit} Jahre, {len(variations_data)} variations", flush=True)
                successful_runs += 1
                total_variations += len(variations_data)
            except Exception as e:
                print(f"[ERROR] Failed to save Laufzeit {laufzeit}: {e}", flush=True)

        print("\n" + "="*80)
        if has_valid_data:
            print(f"[INFO] 🎉 Scraping Complete with VALID DATA!")
        else:
            print(f"[WARN] ⚠️ Scraping Complete but NO VALID DATA extracted!")
            print(f"[WARN] Check screenshots in {SCREENSHOTS_DIR} for debugging")
        print("="*80)
        print(f"[INFO] Successful runs: {successful_runs}/{len(laufzeiten_to_scrape)}")
        print(f"[INFO] Total variations: {total_variations}")
        print("="*80 + "\n")

        return 0 if has_valid_data else 1
    finally:
        context.close()
        browser.close()


def main() -> int:
    try:
        with sync_playwright() as playwright:
            return run(playwright)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
