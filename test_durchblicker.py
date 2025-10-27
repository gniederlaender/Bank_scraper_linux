from __future__ import annotations

import sys
import os
import time
from datetime import datetime
import re
from pathlib import Path
from typing import Dict, List, Any, Optional

from playwright.sync_api import Playwright, sync_playwright, TimeoutError as PlaywrightTimeoutError
from db_helper import save_scraping_data

# Try to load dotenv if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not available, will use environment variables

# Get screenshot directory from environment or use relative path
BASE_DIR = Path(os.getenv('BANKCOMPARISON_BASE_DIR', '.'))
SCREENSHOTS_DIR = Path(os.getenv('SCREENSHOTS_DIR', BASE_DIR / 'screenshots'))


def ensure_dirs() -> None:
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)


def ts_filename(prefix: str) -> str:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{prefix}-{timestamp}.png"


def log_print(label: str, value: str) -> None:
    print(f"{label}: {value}".strip())


def wait_for_text(page, text: str, timeout_ms: int = 15000):
    return page.locator(f"text={text}").first.wait_for(state="visible", timeout=timeout_ms)


def parse_currency_to_float(value: Optional[str]) -> Optional[float]:
    """
    Parse currency string to float
    Examples: "€ 1.948" -> 1948.00, "1.948,50 €" -> 1948.50
    """
    if not value or value == "-":
        return None
    
    # Remove currency symbols and spaces
    value = value.replace("€", "").replace(" ", "").strip()
    
    # German format: 1.234,56 -> 1234.56
    # Remove thousand separators (.) and replace comma with dot
    value = value.replace(".", "")
    value = value.replace(",", ".")
    
    try:
        return float(value)
    except (ValueError, AttributeError):
        return None


def extract_text(page, text_selector: str) -> str:
    locator = page.locator(text_selector).first
    try:
        locator.wait_for(state="visible", timeout=10000)
        return locator.inner_text().strip()
    except PlaywrightTimeoutError:
        return ""


def get_fixierung_values_for_laufzeit(laufzeit_jahre: int) -> List[int]:
    """
    Determine the Fixierung slider values to test based on Laufzeit.
    Rule: Fixierung cannot exceed Laufzeit.
    Returns list of years: 0, 5, 10, 15, etc., up to Laufzeit.
    """
    fixierung_values = []
    current = 0
    while current <= laufzeit_jahre:
        fixierung_values.append(current)
        if current == 0:
            current = 5
        else:
            current += 5
    return fixierung_values


def screen1(page, laufzeit_jahre: int = 35) -> None:
    """
    Screen 1: Set initial parameters
    Note: We set to MAXIMUM Laufzeit (35) here, then adjust on Screen 4
    """
    page.goto("https://durchblicker.at/kreditrechner", wait_until="load")

    # Accept cookies if banner appears
    try:
        # Try common consent button texts
        for attempt in [
            lambda: page.get_by_role("button", name=re.compile(r"alle akzeptieren|akzeptieren|accept all", re.I)).first.click(timeout=2500),
            lambda: page.locator("text=Alle akzeptieren").first.click(timeout=2500),
            lambda: page.locator("text=Akzeptieren").first.click(timeout=2500),
            lambda: page.get_by_role("button", name=re.compile(r"zustimmen|einverstanden", re.I)).first.click(timeout=2500),
        ]:
            try:
                attempt()
                break
            except Exception:
                continue
    except Exception:
        pass

    # Set Kreditbetrag to 500000 (clear first)
    # Try common patterns: labeled input or aria
    def clear_and_type(locator, value: str):
        locator.click()
        page.keyboard.press("Control+A")
        page.keyboard.press("Delete")
        locator.type(value, delay=20)

    filled_amount = False
    for label in [
        "Kreditbetrag",
        "Kreditbetrag in Euro",
        "Kreditbetrag €",
    ]:
        try:
            amount_el = page.get_by_label(label, exact=False)
            if amount_el.count() > 0:
                clear_and_type(amount_el.nth(0), "500000")
                filled_amount = True
                break
        except Exception:
            continue
    if not filled_amount:
        # Fallback: numeric input near text Kreditbetrag
        try:
            kb_section = page.locator("text=Kreditbetrag").first
            input_box = kb_section.locator("xpath=ancestor::section|ancestor::div").locator("input[type='number'], input").first
            clear_and_type(input_box, "500000")
        except Exception:
            pass

    # Set Laufzeit to maximum (35 Jahre) - will be adjusted on Screen 4
    try:
        laufzeit_input = page.locator("#laufzeit").first
        laufzeit_input.wait_for(state="visible", timeout=8000)
        laufzeit_input.click()
        page.keyboard.press("Control+A")
        page.keyboard.press("Delete")
        laufzeit_input.type(str(laufzeit_jahre), delay=50)
        laufzeit_input.blur()
        print(f"[INFO] Laufzeit set to {laufzeit_jahre} via #laufzeit input (max value)", flush=True)
    except Exception as e:
        print(f"[WARN] Could not set Laufzeit via #laufzeit: {e}", flush=True)
        # Fallback
        try:
            lt_section = page.locator("text=Laufzeit").first
            input_box = lt_section.locator("xpath=ancestor::section|ancestor::div").locator("input").first
            input_box.click()
            page.keyboard.press("Control+A")
            page.keyboard.press("Delete")
            input_box.type(str(laufzeit_jahre))
        except Exception:
            pass

    # Give UI a moment to recompute
    time.sleep(1.0)

    # Capture values
    # 1) Repräsentatives Berechnungsbeispiel (longer text)
    rep_text = ""
    for key in [
        "Repräsentatives Berechnungsbeispiel",
        "Repräsentatives Berechnungs Beispiel",
    ]:
        rep_text = extract_text(page, f"text={key}")
        if rep_text:
            # Expand to capture container text if possible
            try:
                container = page.locator(f"text={key}").first.locator("xpath=ancestor::*[self::section or self::div][1]")
                rep_text = container.inner_text().strip()
            except Exception:
                pass
            break

    # 2) Monatliche Rate
    monatliche_rate = ""
    try:
        rate_label = page.locator("text=Monatliche Rate").first
        rate_container = rate_label.locator("xpath=ancestor::*[self::section or self::div][1]")
        monatliche_rate = rate_container.inner_text().strip()
    except Exception:
        # Fallback: look for euro amount near label
        try:
            monatliche_rate = page.locator("text=€").first.inner_text().strip()
        except Exception:
            pass

    # 3) zB. Fixzins für 25 Jahre
    fixzins_25 = ""
    for key in [
        "Fixzins für 25 Jahre",
        "Fixzins 25",
        "zb. Fixzins für 25 Jahre",
        "zB. Fixzins für 25 Jahre",
    ]:
        fixzins_25 = extract_text(page, f"text={key}")
        if fixzins_25:
            try:
                container = page.locator(f"text={key}").first.locator("xpath=ancestor::*[self::section or self::div][1]")
                fixzins_25 = container.inner_text().strip()
            except Exception:
                pass
            break

    log_print("Repräsentatives Berechnungsbeispiel", rep_text)
    log_print("Monatliche Rate", monatliche_rate)
    log_print("Fixzins (25 Jahre)", fixzins_25)

    # Screenshot
    page.screenshot(path=str(SCREENSHOTS_DIR / ts_filename("screen1")), full_page=True)

    # Click "Jetzt berechnen"
    for name in [
        "Jetzt berechnen",
        "Berechnen",
    ]:
        try:
            page.get_by_role("button", name=name).first.click(timeout=5000)
            break
        except Exception:
            continue


def _verify_selection(page, container, value_text: str) -> bool:
    # Check radio/tiles via aria-checked
    try:
        radio_checked = container.locator("[role='radio'][aria-checked='true']").filter(has_text=value_text)
        if radio_checked.count() > 0:
            return True
    except Exception:
        pass
    # Check native select selected option text
    try:
        select_el = container.locator("select").first
        if select_el.count() > 0:
            try:
                option_text = select_el.locator("option:checked").inner_text().strip()
                return value_text.lower() in option_text.lower()
            except Exception:
                pass
    except Exception:
        pass
    # Check combobox selected flag
    try:
        selected_option = container.locator("[aria-selected='true']").filter(has_text=value_text)
        if selected_option.count() > 0:
            return True
    except Exception:
        pass
    return False


def set_select_like(page, label_text: str, value_text: str) -> bool:
    print(f"[INFO] Set select '{label_text}' -> '{value_text}' (start)", flush=True)
    # Try accessible select first
    try:
        select_el = page.get_by_label(label_text, exact=False)
        if select_el.count() > 0:
            try:
                select_el.select_option(label=value_text, timeout=6000)
                print(f"[INFO] Set select '{label_text}' done (accessible)", flush=True)
                return True
            except Exception:
                pass
    except Exception:
        pass
    # Fallback: click dropdown/tiles by label then option by text
    try:
        label_node = page.locator(f"text={label_text}").first
        label_node.scroll_into_view_if_needed(timeout=4000)
        container = label_node.locator("xpath=ancestor::*[self::label or self::section or self::div or self::fieldset][1]")
        # Try tiles/radios/buttons
        tile = container.locator("[role='radio'][aria-label='" + value_text + "'], [role='radio']:has-text('" + value_text + "'), button:has-text('" + value_text + "'), [role='button']:has-text('" + value_text + "')").first
        if tile.count() > 0:
            tile.scroll_into_view_if_needed(timeout=4000)
            tile.click(timeout=6000)
            if _verify_selection(page, container, value_text):
                print(f"[INFO] Set select '{label_text}' done (tile/radio)", flush=True)
                return True
        # Native select
        native_select = container.locator("select").first
        if native_select.count() > 0:
            try:
                native_select.select_option(label=value_text, timeout=6000)
                if _verify_selection(page, container, value_text):
                    print(f"[INFO] Set select '{label_text}' done (native)", flush=True)
                    return True
            except Exception:
                pass
        # Combobox/button-like triggers
        trigger = container.locator("select, [role='combobox'], button, [role='button'], .select__control, .dropdown-toggle").first
        trigger.scroll_into_view_if_needed(timeout=4000)
        trigger.click(timeout=6000)
        try:
            page.get_by_role("option", name=value_text).first.click(timeout=4000)
        except Exception:
            page.locator(f"text={value_text}").first.click(timeout=4000)
        if _verify_selection(page, container, value_text):
            print(f"[INFO] Set select '{label_text}' done (fallback)", flush=True)
            return True
    except Exception:
        # Last resort: click option by text directly
        try:
            page.locator(f"text={value_text}").first.click(timeout=6000)
            try:
                label_node = page.locator(f"text={label_text}").first
                container = label_node.locator("xpath=ancestor::*[self::label or self::section or self::div or self::fieldset][1]")
                if _verify_selection(page, container, value_text):
                    print(f"[INFO] Set select '{label_text}' done (direct)", flush=True)
                    return True
            except Exception:
                pass
        except Exception:
            print(f"[WARN] Set select '{label_text}' failed", flush=True)
    return False


def fill_number_near_label(page, label_text: str, value: str) -> None:
    print(f"[INFO] Fill number '{label_text}' -> '{value}' (start)", flush=True)
    # Accessible label
    try:
        page.get_by_label(label_text, exact=False).fill(value, timeout=6000)
        print(f"[INFO] Fill number '{label_text}' done (accessible)", flush=True)
        return
    except Exception:
        pass
    # Fallback near label
    try:
        label_node = page.locator(f"text={label_text}").first
        container = label_node.locator("xpath=ancestor::*[self::label or self::section or self::div][1]")
        input_box = container.locator("input[type='number'], input").first
        input_box.fill(value, timeout=6000)
        print(f"[INFO] Fill number '{label_text}' done (fallback)", flush=True)
    except Exception:
        print(f"[WARN] Fill number '{label_text}' failed", flush=True)


def screen2(page) -> None:
    # Wait for screen 2 elements
    try:
        wait_for_text(page, "Finanzierungsvorhaben", timeout_ms=20000)
    except PlaywrightTimeoutError:
        pass

    # Give UI time to render and verify markers
    time.sleep(3)
    try:
        page.locator("text=Finanzierungsvorhaben").first.wait_for(state="visible", timeout=6000)
        page.locator("text=Art der Immobilie").first.wait_for(state="visible", timeout=6000)
    except Exception:
        print("[WARN] Screen 2 markers not visible; taking debug screenshot", flush=True)
        page.screenshot(path=str(SCREENSHOTS_DIR / ts_filename("screen2-debug")), full_page=True)

    print("[INFO] Screen 2 interactions start", flush=True)
    # First try direct known select element for Finanzierungsvorhaben
    success_fv = False
    try:
        sel = page.locator("#select_immokredit_projekt_vorhaben").first
        if sel.count() > 0:
            sel.select_option(value="kauf", timeout=6000)
            try:
                checked_text = sel.locator("option:checked").inner_text().strip()
                if "kauf" in sel.input_value().lower() or "kauf" in checked_text.lower():
                    print("[INFO] Finanzierungsvorhaben set via direct select (id)", flush=True)
                    success_fv = True
            except Exception:
                pass
    except Exception:
        pass
    if not success_fv:
        success_fv = set_select_like(page, "Finanzierungsvorhaben", "Kauf")
    if not success_fv:
        print("[ERROR] Finanzierungsvorhaben could not be set. Aborting further steps on Screen 2.", flush=True)
        page.screenshot(path=str(SCREENSHOTS_DIR / ts_filename("screen2-fv-failed")), full_page=True)
        return
    # Direct selects via IDs from provided page source
    try:
        page.locator("#select_immokredit_projekt_suchphaseKauf").first.select_option(value="recherche", timeout=6000)
        print("[INFO] Suchphase set (id)", flush=True)
    except Exception:
        set_select_like(page, "Suchphase", "Recherche")
    try:
        page.locator("#select_immokredit_projekt_immobilie").first.select_option(value="wohnung", timeout=6000)
        print("[INFO] Art der Immobilie set (id)", flush=True)
    except Exception:
        set_select_like(page, "Art der Immobilie", "Eigentumswohnung")
    try:
        page.locator("#select_immokredit_projekt_inBau").first.select_option(value="fertig", timeout=6000)
        print("[INFO] Immobilie in Bau set (id)", flush=True)
    except Exception:
        set_select_like(page, "Immobilie in Bau", "bestehende Immobilie")
    try:
        page.locator("#select_immokredit_projekt_lage").first.select_option(value="wien", timeout=6000)
        print("[INFO] Lage der Immobilie set (id)", flush=True)
    except Exception:
        set_select_like(page, "Lage der Immobilie", "Wien")
    try:
        page.locator("#select_immokredit_projekt_nutzung").first.select_option(value="eigen", timeout=6000)
        print("[INFO] Nutzung set (id)", flush=True)
    except Exception:
        set_select_like(page, "Nutzung", "Eigennutzung")

    # Direct inputs via IDs
    def clear_type_and_blur(selector: str, value: str) -> None:
        el = page.locator(selector).first
        el.wait_for(state="visible", timeout=8000)
        el.click()
        page.keyboard.press("Control+A")
        page.keyboard.press("Delete")
        el.type(value, delay=20)
        el.blur()

    try:
        clear_type_and_blur("#input_immokredit_projektkosten_kaufpreis", "500000")
        print("[INFO] Kaufpreis set (id)", flush=True)
    except Exception:
        fill_number_near_label(page, "Kaufpreis", "500000")
    try:
        clear_type_and_blur("#input_immokredit_projektkosten_kaufnebenkosten", "50000")
        print("[INFO] Kaufnebenkosten set (id)", flush=True)
    except Exception:
        fill_number_near_label(page, "Kaufnebenkosten", "50000")
    try:
        clear_type_and_blur("#input_immokredit_projektkosten_eigenmittel", "150000")
        print("[INFO] Eigenmittel set (id)", flush=True)
    except Exception:
        fill_number_near_label(page, "Eigenmittel", "150000")
    print("[INFO] Screen 2 interactions done", flush=True)

    time.sleep(0.5)
    page.screenshot(path=str(SCREENSHOTS_DIR / ts_filename("screen2")), full_page=True)

    for name in ["Weiter", "Nächster Schritt", "Fortfahren"]:
        try:
            page.get_by_role("button", name=name).first.click(timeout=6000)
            break
        except Exception:
            continue


def screen3(page) -> None:
    try:
        wait_for_text(page, "Ihr Alter", timeout_ms=20000)
    except PlaywrightTimeoutError:
        pass

    def first_visible_locator(selectors: list[str]):
        for sel in selectors:
            loc = page.locator(sel).first
            try:
                if loc.count() > 0:
                    loc.wait_for(state="visible", timeout=2000)
                    return loc
            except Exception:
                continue
        return None

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

    print("[INFO] Screen 3 ID-based fill start", flush=True)
    # Ihr Alter
    if not clear_type_and_blur("input[id*='haushalt'][id*='alter'], #input_immokredit_haushalt_alter", "45"):
        fill_number_near_label(page, "Ihr Alter", "45")

    # Finanzierung mit zweiter Person -> Nein
    try:
        container = first_visible_locator([
            "div.row[data-storage*='haushalt'][data-storage*='zweite']",
            "div.row:has-text('Finanzierung mit zweiter Person')",
        ])
        if container:
            radio_no = container.locator("input[type='radio'][value='false'], label:has-text('Nein')").first
            radio_no.click()
        else:
            page.get_by_role("radio", name=lambda n: n and "nein" in n.lower()).first.check()
    except Exception:
        try:
            page.get_by_role("button", name=lambda n: n and "nein" in n.lower()).first.click()
        except Exception:
            pass

    # Anzahl unterhaltspflichtiger Kinder -> Keine
    sel_kinder = first_visible_locator([
        "select[id*='haushalt'][id*='kinder']",
        "#select_immokredit_haushalt_kinder",
    ])
    if sel_kinder:
        try:
            sel_kinder.select_option(label="Keine", timeout=6000)
        except Exception:
            try:
                sel_kinder.select_option(value="keine", timeout=6000)
            except Exception:
                set_select_like(page, "Anzahl unterhaltspflichtiger Kinder", "Keine")
    else:
        set_select_like(page, "Anzahl unterhaltspflichtiger Kinder", "Keine")

    # Ihre berufliche Situation -> Angestellt / Arbeitend via known id
    try:
        page.locator("#select_immokredit_haushalt_berufsituation").first.select_option(value="erwerb", timeout=6000)
        print("[INFO] Berufssituation set (id)", flush=True)
    except Exception:
        sel_beruf = first_visible_locator([
            "select[id*='haushalt'][id*='beruf']",
            "select[id*='berufliche']",
        ])
        if sel_beruf:
            try:
                sel_beruf.select_option(label="Angestellt", timeout=6000)
            except Exception:
                try:
                    sel_beruf.select_option(value="angestellt", timeout=6000)
                except Exception:
                    set_select_like(page, "Ihre berufliche Situation", "Angestellt")
        else:
            set_select_like(page, "Ihre berufliche Situation", "Angestellt")

    # Ihr Netto-Einkommen -> 8500 (via known id, requires special handling due to blur event)
    print("[INFO] Setting Netto-Einkommen...", flush=True)
    try:
        einkommen_input = page.locator("#input_immokredit_haushalt_einkommen").first
        einkommen_input.wait_for(state="visible", timeout=8000)
        einkommen_input.click()
        time.sleep(0.3)  # Small delay after click
        page.keyboard.press("Control+A")
        page.keyboard.press("Delete")
        time.sleep(0.2)
        einkommen_input.type("8500", delay=50)
        time.sleep(0.3)
        einkommen_input.blur()  # Trigger the blur event that sets the value
        time.sleep(0.5)  # Wait for JS to process
        print("[INFO] Netto-Einkommen set via direct input", flush=True)
    except Exception as e:
        print(f"[WARN] Could not set Netto-Einkommen: {e}", flush=True)
        try:
            fill_number_near_label(page, "Ihr Netto-Einkommen", "8500")
        except Exception:
            pass

    # Wohnnutzfläche -> 100 via known id
    if not clear_type_and_blur("#input_immokredit_haushalt_nutzflaeche", "100"):
        if not clear_type_and_blur("input[id*='wohn'][id*='flae'], input[id*='wohn'][id*='nutz']", "100"):
            fill_number_near_label(page, "Wohnnutzfläche", "100")

    # Kredit-/Leasingraten -> 300
    if not clear_type_and_blur("input[id*='leasing'], input[id*='kredit'][id*='rate']", "300"):
        fill_number_near_label(page, "Kredit-/Leasingraten", "300")

    # Anzahl der KFZ -> Keine
    sel_kfz = first_visible_locator([
        "select[id*='kfz']",
        "#select_immokredit_haushalt_kfz",
    ])
    if sel_kfz:
        try:
            sel_kfz.select_option(label="keine", timeout=6000)
        except Exception:
            try:
                sel_kfz.select_option(value="none", timeout=6000)
            except Exception:
                set_select_like(page, "Anzahl der KFZ", "Keine")
    else:
        set_select_like(page, "Anzahl der KFZ", "Keine")

    print("[INFO] Screen 3 ID-based fill done", flush=True)

    time.sleep(0.5)
    page.screenshot(path=str(SCREENSHOTS_DIR / ts_filename("screen3")), full_page=True)

    print("[INFO] Attempting to click Berechnen button...", flush=True)
    for name in ["Berechnen", "Jetzt berechnen", "Angebote berechnen"]:
        try:
            page.get_by_role("button", name=name).first.click(timeout=5000)
            print(f"[INFO] Clicked '{name}' button", flush=True)
            break
        except Exception as e:
            print(f"[WARN] Failed to click '{name}': {e}", flush=True)
            continue
    
    # Wait a moment and check for validation errors
    time.sleep(2)
    try:
        error_elements = page.locator(".alert-danger, .error, [class*='error'], [class*='danger']")
        if error_elements.count() > 0:
            for i in range(error_elements.count()):
                error_text = error_elements.nth(i).inner_text()
                if error_text.strip():
                    print(f"[WARN] Validation error found: {error_text.strip()}", flush=True)
    except Exception as e:
        print(f"[DEBUG] Error checking for validation messages: {e}", flush=True)


def screen4(page, laufzeiten_to_scrape: List[int] = None) -> Dict[int, List[Dict[str, Any]]]:
    """
    Screen 4: Results page with TWO sliders (Laufzeit and Fixierung)
    This function stays on Screen 4 and toggles BOTH sliders to capture all combinations.
    
    Args:
        page: Playwright page object
        laufzeiten_to_scrape: List of Laufzeiten to scrape (default: [35, 30, 25, 20, 15])
    
    Returns:
        Dict mapping laufzeit -> list of variations
    """
    if laufzeiten_to_scrape is None:
        laufzeiten_to_scrape = [35, 30, 25, 20, 15]
    
    # Wait for results to load (look for typical result elements)
    try:
        page.wait_for_load_state("networkidle", timeout=30000)
    except PlaywrightTimeoutError:
        pass

    # Heuristic wait for offers/summary
    for key in [
        "Kreditangebote",
        "Ergebnisse",
        "Angebote",
    ]:
        try:
            wait_for_text(page, key, timeout_ms=8000)
            break
        except PlaywrightTimeoutError:
            continue

    def scrape_offer_details() -> dict:
        """Scrape financial data specifically from the Finanzierungsdetails div element"""
        details = {}
        try:
            # Target the specific Finanzierungsdetails div element
            finanzierung_div = page.locator('[data-sentry-component="Finanzierungsdetails"]').first
            
            if finanzierung_div.count() == 0:
                print("[WARN] Finanzierungsdetails div not found", flush=True)
                return details
            
            # Wait for the element to be visible
            finanzierung_div.wait_for(state="visible", timeout=10000)
            
            # Get all the grid rows within the Finanzierungsdetails div
            grid_rows = finanzierung_div.locator('div.grid.grid-cols-subgrid')
            
            print(f"[DEBUG] Found {grid_rows.count()} financial data rows", flush=True)
            
            # Extract data from each row
            for i in range(grid_rows.count()):
                row = grid_rows.nth(i)
                
                # Get the label (first div) and value (third div with span)
                label_div = row.locator('div').first
                value_span = row.locator('div.text-bluegrey span').first
                
                if label_div.count() > 0 and value_span.count() > 0:
                    label = label_div.inner_text().strip()
                    value = value_span.inner_text().strip()
                    
                    if label and value:
                        # Clean up the label to match our expected keys
                        clean_label = label.replace('Anschlusskondition nach Fixzinsphase', 'Anschlusskondition')
                        details[clean_label] = value
                        print(f"[DEBUG] Extracted {clean_label}: {value}", flush=True)
            
            # Also check for any additional fields that might be in different structures
            if not details:
                print("[WARN] No data extracted from structured grid, trying fallback...", flush=True)
                # Fallback to text-based extraction if structured approach fails
                full_text = finanzierung_div.inner_text()
                print(f"[DEBUG] Finanzierungsdetails text: {full_text[:500]}...", flush=True)
                
        except Exception as e:
            print(f"[WARN] Error scraping Finanzierungsdetails: {e}", flush=True)
        
        return details
    
    def set_laufzeit_slider(value: int) -> None:
        """Set the Laufzeit slider on Screen 4 to a specific value"""
        try:
            slider = page.locator("#laufzeitslider").first
            slider.wait_for(state="visible", timeout=8000)
            slider.fill(str(value))
            # Trigger change event
            slider.dispatch_event("change")
            slider.dispatch_event("input")
            # Wait for UI to update
            time.sleep(2)
            print(f"[INFO] Laufzeit slider set to {value} years", flush=True)
        except Exception as e:
            print(f"[WARN] Error setting Laufzeit slider to {value}: {e}", flush=True)
    
    def set_fixierung_slider(value: int) -> None:
        """Set the Fixierung slider to a specific value (fixed interest period in years)"""
        try:
            slider = page.locator("#fixverzinsungslider").first
            slider.wait_for(state="visible", timeout=8000)
            slider.fill(str(value))
            # Trigger change event
            slider.dispatch_event("change")
            slider.dispatch_event("input")
            # Wait for UI to update
            time.sleep(2)
            print(f"[INFO] Fixierung slider set to {value} years", flush=True)
        except Exception as e:
            print(f"[WARN] Error setting Fixierung slider to {value}: {e}", flush=True)
    
    # Dictionary to store all variations organized by Laufzeit
    all_data_by_laufzeit = {}
    
    # Loop through each Laufzeit (descending order: 35, 30, 25, 20, 15...)
    for laufzeit in laufzeiten_to_scrape:
        print("\n" + "="*70)
        print(f"[INFO] Processing Laufzeit: {laufzeit} Jahre (on Screen 4)")
        print("="*70)
        
        # Set the Laufzeit slider on Screen 4
        set_laufzeit_slider(laufzeit)
        
        # Determine appropriate Fixierung values for this Laufzeit
        fixierung_values = get_fixierung_values_for_laufzeit(laufzeit)
        print(f"[INFO] Fixierung values for {laufzeit} Jahre: {fixierung_values}", flush=True)
        
        variations_data = []
        
        # Loop through each Fixierung value
        for fixierung in fixierung_values:
            print(f"\n[INFO] Setting Fixierung to {fixierung} years (Laufzeit: {laufzeit})...", flush=True)
            set_fixierung_slider(fixierung)
            
            # Wait a moment for the UI to update
            time.sleep(1)
            
            # Scrape details
            print(f"[INFO] Capturing data at {laufzeit}J Laufzeit / {fixierung}J Fixierung...", flush=True)
            details = scrape_offer_details()
            
            if details and any(v != '-' for v in details.values()):
                print(f"[INFO] Data captured successfully:", flush=True)
                for key, val in details.items():
                    if val != '-':
                        print(f"  {key}: {val}", flush=True)
            else:
                print(f"[WARN] No data captured or all fields empty", flush=True)
            
            # Convert to structured format
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
                'gesamtbetrag': parse_currency_to_float(details.get('Zu zahlender Gesamtbetrag')),
                'besicherung': details.get('Besicherung', '-')
            }
            variations_data.append(variation_data)
            
            # Take screenshot
            screenshot_name = f"screen4_laufzeit_{laufzeit}j_fixierung_{fixierung}j"
            page.screenshot(path=str(SCREENSHOTS_DIR / ts_filename(screenshot_name)), full_page=True)
            print(f"[INFO] Screenshot: {screenshot_name}", flush=True)
        
        # Store variations for this Laufzeit
        all_data_by_laufzeit[laufzeit] = variations_data
        print(f"\n[INFO] ✓ Laufzeit {laufzeit} Jahre complete: {len(variations_data)} variations captured")
    
    # Take final screenshot
    page.screenshot(path=str(SCREENSHOTS_DIR / ts_filename("screen4_final")), full_page=True)
    
    return all_data_by_laufzeit


def run(playwright: Playwright) -> int:
    ensure_dirs()
    browser = playwright.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])  # headless runner friendly
    context = browser.new_context(locale="de-DE")
    page = context.new_page()
    # Make failures surface faster
    page.set_default_timeout(15000)
    
    # Define Laufzeiten to scrape (descending order for Screen 4 slider)
    # Current range: 35, 30, 25, 20, 15 (can expand to include 10, 5)
    laufzeiten_to_scrape = [35, 30, 25, 20, 15]
    
    # Start with MAXIMUM Laufzeit for Screen 1
    max_laufzeit = max(laufzeiten_to_scrape)
    
    # Base metadata (same for all runs)
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
        print(f"[INFO] Multi-Laufzeit Scraping Session Started")
        print(f"[INFO] Will scrape Laufzeiten: {laufzeiten_to_scrape}")
        print("="*80 + "\n")
        
        # Navigate through Screens 1-3 ONCE with maximum Laufzeit
        print(f"[INFO] Screen 1 start (Initial Laufzeit: {max_laufzeit} Jahre)", flush=True)
        screen1(page, laufzeit_jahre=max_laufzeit)
        print("[INFO] Screen 1 done", flush=True)
        
        print("[INFO] Screen 2 start", flush=True)
        screen2(page)
        print("[INFO] Screen 2 done", flush=True)
        
        print("[INFO] Screen 3 start", flush=True)
        screen3(page)
        print("[INFO] Screen 3 done", flush=True)
        
        # Screen 4: Toggle both sliders to capture ALL Laufzeit/Fixierung combinations
        print("[INFO] Screen 4 start (will process all Laufzeiten here)", flush=True)
        all_data_by_laufzeit = screen4(page, laufzeiten_to_scrape=laufzeiten_to_scrape)
        print("[INFO] Screen 4 done - All Laufzeiten processed", flush=True)
        
        # Save each Laufzeit as a separate database run
        print("\n" + "="*80)
        print("[INFO] Saving data to database...")
        print("="*80)
        
        successful_runs = 0
        total_variations = 0
        
        for laufzeit, variations_data in all_data_by_laufzeit.items():
            run_metadata = base_metadata.copy()
            run_metadata['scrape_date'] = datetime.now()
            run_metadata['laufzeit_jahre'] = laufzeit
            run_metadata['notes'] = f'Multi-Laufzeit scraping (Screen 4 sliders) - {laufzeit} Jahre'
            
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
        print(f"[INFO] 🎉 Multi-Laufzeit Scraping Complete!")
        print("="*80)
        print(f"[INFO] Successful runs: {successful_runs}/{len(laufzeiten_to_scrape)}")
        print(f"[INFO] Total variations captured: {total_variations}")
        print(f"[INFO] Laufzeiten scraped: {list(all_data_by_laufzeit.keys())}")
        print("="*80 + "\n")
        
        return 0
    finally:
        context.close()
        browser.close()


def main() -> int:
    try:
        with sync_playwright() as playwright:
            return run(playwright)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())


