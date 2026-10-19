"""Durchblicker.at housing loan (Immokredit) scraper — direct API approach.

Durchblicker rebuilt their Kreditrechner frontend (Next.js widget + wizard),
which broke the previous Playwright-based UI automation. Instead of driving
the form, this scraper calls the calculation API the wizard itself uses:

    POST https://durchblicker.at/api/0.2/tariff-calculate/immokredit

The endpoint accepts the full wizard input as JSON and synchronously returns
the best-offer calculation (Rate, Sollzins, Effektivzins, Anschlusskondition,
Auszahlungsbetrag, eingerechnete Kosten, Gesamtbelastung, Besicherung).

Transport: durchblicker.at sits behind Cloudflare, which answers plain HTTP
clients (python-requests, curl) from our Hetzner server with 403 "Sorry, you
have been blocked". A normal headless Chromium is let through. So the scraper
opens durchblicker.at once in Playwright and issues the API calls with fetch()
from inside the page (same origin, exactly like the wizard does). No form
interaction, no cookie banner handling needed.

The household/project parameters below mirror the values the old UI scraper
entered, so the stored time series stays comparable:
  Kaufpreis 500.000, Nebenkosten 50.000, Eigenmittel 150.000 (=> Finanzierung
  400.000), Wohnung/fertig/Wien/Eigennutzung, 1 Kreditnehmer, 45 Jahre,
  Einkommen 8.500, Nutzflaeche 100 m2, bestehende Kreditraten 300.

For each Laufzeit in LAUFZEITEN_TO_SCRAPE all Fixierung variants
(0 = variabel, then 5, 10, ... up to Laufzeit) are calculated and written to
the database in the same format the previous scraper produced, so
create_housing_loan_view.py / generate_housing_loan_html.py keep working.
"""

from __future__ import annotations

import copy
import json
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from playwright.sync_api import Error as PlaywrightError, sync_playwright

from db_helper import save_scraping_data

# Try to load dotenv if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

API_URL = "https://durchblicker.at/api/0.2/tariff-calculate/immokredit"

LANDING_URL = "https://durchblicker.at/immobilienfinanzierung"
BROWSER_ARGS = [
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-setuid-sandbox",
]

LAUFZEITEN_TO_SCRAPE = [35, 30, 25, 20, 15]

# The API rate-limits roughly 20 calls per minute (HTTP 429, no Retry-After
# header), so calls are spaced out and 429s get long backoffs.
REQUEST_TIMEOUT = 60
MAX_RETRIES = 5
RETRY_BACKOFF = [2, 4, 8, 16, 16]
RATE_LIMIT_BACKOFF = [30, 60, 90, 120, 120]
DELAY_BETWEEN_CALLS = 4.0

# Wizard input as captured from durchblicker.at ("Kauf Wohnung in Wien").
# projekt.laufzeit / projekt.fixverzinsung(Boolean) are set per variation.
BASE_INPUT: Dict[str, Any] = {
    "input": {
        "immokredit": {
            "projekt": {
                "vorhaben": "kauf",
                "suchphaseKauf": "recherche",
                "suchphaseUmbau": "none",
                "suchphaseUmschuldung": "none",
                "immobilie": "wohnung",
                "gefunden": True,
                "suchphaseBau": "none",
                "eigentumsform": "eigentum",
                "pacht": 0,
                "pfandrechthoehe": 0,
                "grundstueck": 0,
                "wertimmobilie": 0,
                "wertdachboden": 0,
                "grundstueckgefunden": True,
                "inBau": "fertig",
                "lage": "wien",
                "nutzung": "eigen",
                "angebot": False,
                "foerderungbesteht": False,
                "foerderungneu": False,
                "laufzeit": "35",
                "fixverzinsungBoolean": False,
                "fixverzinsung": 0,
            },
            "projektkosten": {
                "kaufpreis": 500000,
                "kaufnebenkosten": 50000,
                "kaufnebenkosteninfo": False,
                "kaufpreisgrundstueck": 0,
                "kaufpreisdachboden": 0,
                "kaufnebenkostengrundstueck": 0,
                "kaufnebenkostendachboden": 0,
                "baukosten": 0,
                "genossenschaftsanteil": 0,
                "umbauprojektkosten": 0,
                "adaptierungskosten": 0,
                "sonstige": 0,
                "gesamt": 550000,
                "foerderung": 0,
                "foerderungzurueck": True,
                "eigenmittel": 150000,
                "eigenmittelinfo": False,
                "finanzierung": 400000,
                "finanzierunggesamt": 400000,
                "genossenschaftinfo": False,
                "bankbestehend": "none",
                "kredithoehe": 0,
                "zusatzbetragaktiv": False,
                "zusatzbetrag": 0,
                "restlaufzeit": "25",
                "ratebestehend": 0,
            },
            "haushalt": {
                "sicherheiten": "none",
                "sicherheitwert": 0,
                "alter": 45,
                "beziehung": "none",
                "alterpartner": 0,
                "kinder": 0,
                "privatkonkurs": False,
                "berufsituation": "erwerb",
                "selbststaendigkeitdauer": True,
                "freiberufler": False,
                "einkommen": 8500,
                "einkommeninfo": False,
                "berufsituationpartner": "none",
                "selbststaendigkeitdauerpartner": True,
                "freiberuflerpartner": False,
                "einkommenpartner": 0,
                "einkommenpartnerinfo": False,
                "einkommengemeinsam": 8500,
                "beschaeftigungsdauer": True,
                "mieteinnahmen": 0,
                "buerge": False,
                "buergeinfo": False,
                "einkommenbuerge": 0,
                "nutzflaeche": 100,
                "mietausgaben": 0,
                "wohnkosten": 0,
                "rueckzahlungfoerderung": 0,
                "ratebestehend": 300,
                "alimente": 0,
                "sonderausgaben": 300,
                "anzahlkfz": 0,
                "zweiteperson": False,
            },
        },
        "section": {},
        "mydb": {"hasForeignDO": False},
        "submitted": {"input-projekt": True, "input-haushalt": True},
        "verified": {"input-projekt": True, "input-haushalt": True},
        "captcha": "",
        "berechnet": True,
    },
    "userid": "",
    "src": "calc",
    "captcha": "",
    "hostname": "durchblicker.at",
    "isMobile": False,
    "gclid": None,
}


def get_fixierung_values_for_laufzeit(laufzeit_jahre: int) -> List[int]:
    """Fixierung values to calculate: 0 (variabel), 5, 10, ... up to Laufzeit."""
    fixierung_values = []
    current = 0
    while current <= laufzeit_jahre:
        fixierung_values.append(current)
        current = 5 if current == 0 else current + 5
    return fixierung_values


def build_input(laufzeit_jahre: int, fixierung_jahre: int) -> Dict[str, Any]:
    payload = copy.deepcopy(BASE_INPUT)
    projekt = payload["input"]["immokredit"]["projekt"]
    projekt["laufzeit"] = str(laufzeit_jahre)
    if fixierung_jahre > 0:
        projekt["fixverzinsungBoolean"] = True
        projekt["fixverzinsung"] = fixierung_jahre
    else:
        projekt["fixverzinsungBoolean"] = False
        projekt["fixverzinsung"] = 0
    return payload


def de_number(value: float, decimals: int = 3) -> str:
    """Format a number with German decimal comma (no thousand separators)."""
    return f"{value:.{decimals}f}".replace(".", ",")


class BlockedError(RuntimeError):
    """durchblicker.at / Cloudflare refuses our browser session - stop the run."""


class BrowserApi:
    """Calls the tariff-calculate API via fetch() inside a durchblicker.at page."""

    JS_FETCH = """async ([url, payload, timeoutMs]) => {
        const ctrl = new AbortController();
        const t = setTimeout(() => ctrl.abort(), timeoutMs);
        try {
            const r = await fetch(url, {
                method: 'POST',
                headers: {'content-type': 'application/json'},
                body: JSON.stringify(payload),
                signal: ctrl.signal,
            });
            return {status: r.status, text: await r.text()};
        } catch (e) {
            return {status: 0, text: String(e)};
        } finally {
            clearTimeout(t);
        }
    }"""

    def __init__(self, playwright) -> None:
        self.browser = playwright.chromium.launch(headless=True, args=BROWSER_ARGS)
        self.context = self.browser.new_context(locale="de-AT")
        self.page = self.context.new_page()
        self.open_landing()

    def open_landing(self) -> None:
        response = self.page.goto(LANDING_URL, wait_until="domcontentloaded", timeout=60000)
        status = response.status if response else None
        print(f"[INFO] Opened {LANDING_URL} (HTTP {status})", flush=True)
        if status != 200:
            raise BlockedError(
                f"durchblicker.at landing page returned HTTP {status} - "
                "browser access blocked?"
            )

    def post(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self.page.evaluate(
            self.JS_FETCH, [API_URL, payload, REQUEST_TIMEOUT * 1000]
        )

    def close(self) -> None:
        try:
            self.browser.close()
        except PlaywrightError:
            pass


def fetch_offer(
    api: BrowserApi, laufzeit_jahre: int, fixierung_jahre: int
) -> Optional[Dict[str, Any]]:
    """Call the tariff-calculate API for one Laufzeit/Fixierung combination."""
    payload = build_input(laufzeit_jahre, fixierung_jahre)
    last_error: Optional[str] = None

    for attempt in range(MAX_RETRIES):
        rate_limited = False
        try:
            response = api.post(payload)
            status = response.get("status")
            if status == 429:
                rate_limited = True
                last_error = "HTTP 429 (rate limited)"
            elif status != 200:
                last_error = f"HTTP {status}: {response.get('text', '')[:120]}"
                if status == 403:
                    if attempt > 0:
                        raise BlockedError(f"API still HTTP 403 after page reload")
                    # Session may have been flagged; reload the landing page once
                    # (raises BlockedError if the page itself is now blocked).
                    api.open_landing()
            else:
                body = json.loads(response["text"])
                if body.get("success") and body.get("result"):
                    return body["result"][0]
                last_error = (
                    f"success={body.get('success')} message={body.get('message')}"
                )
        except BlockedError:
            raise
        except (PlaywrightError, ValueError, KeyError) as exc:
            last_error = str(exc)

        if attempt < MAX_RETRIES - 1:
            backoff = RATE_LIMIT_BACKOFF if rate_limited else RETRY_BACKOFF
            wait = backoff[min(attempt, len(backoff) - 1)]
            print(
                f"[WARN] API call failed ({last_error}), retrying in {wait}s...",
                flush=True,
            )
            time.sleep(wait)

    print(
        f"[ERROR] API call failed for Laufzeit {laufzeit_jahre}/Fixierung "
        f"{fixierung_jahre}: {last_error}",
        flush=True,
    )
    return None


def offer_to_variation(
    offer: Optional[Dict[str, Any]], laufzeit_jahre: int, fixierung_jahre: int
) -> Dict[str, Any]:
    """Map an API result to the fixierung_variations row format.

    Text fields mimic the strings the old UI scraper captured
    (e.g. "3,290 % p.a. variabel", "4,080 % p.a. fix (25 Jahre)") so the
    housing_loan_chart_ready view keeps parsing them correctly.
    """
    if not offer:
        return {
            "fixierung_jahre": fixierung_jahre,
            "rate": None,
            "zinssatz": "-",
            "laufzeit": f"{laufzeit_jahre} Jahre",
            "anschlusskondition": None,
            "effektiver_zinssatz": "-",
            "auszahlungsbetrag": None,
            "einberechnete_kosten": None,
            "kreditbetrag": None,
            "gesamtbetrag": None,
            "besicherung": "-",
            "bank_id": None,
            "euribor": None,
            "euribor_typ": None,
        }

    zins = offer.get("zins")
    eff_zins = offer.get("effektivZins")
    anschluss = offer.get("anschlusskondition")

    if fixierung_jahre > 0:
        zinssatz_text = (
            f"{de_number(zins)} % p.a. fix ({fixierung_jahre} Jahre)"
            if zins is not None
            else "-"
        )
        anschluss_text = (
            f"{de_number(anschluss)} % p.a. variabel" if anschluss is not None else None
        )
    else:
        zinssatz_text = (
            f"{de_number(zins)} % p.a. variabel" if zins is not None else "-"
        )
        anschluss_text = None

    return {
        "fixierung_jahre": fixierung_jahre,
        "rate": offer.get("rate"),
        "zinssatz": zinssatz_text,
        "laufzeit": f"{offer.get('laufzeit', laufzeit_jahre)} Jahre",
        "anschlusskondition": anschluss_text,
        "effektiver_zinssatz": (
            f"{de_number(eff_zins)} % p.a." if eff_zins is not None else "-"
        ),
        "auszahlungsbetrag": offer.get("auszahlungsbetrag"),
        "einberechnete_kosten": offer.get("eingerechneteKosten"),
        "kreditbetrag": offer.get("kreditbetrag"),
        "gesamtbetrag": offer.get("gesamtbelastung"),
        "besicherung": offer.get("besicherung", "-"),
        # Anonymous Durchblicker-internal ID of the bank behind the best
        # offer (no public name mapping) plus the Euribor reference rate
        # the variable pricing is based on (euribor_typ = months, e.g. 3).
        "bank_id": offer.get("bank"),
        "euribor": offer.get("euribor"),
        "euribor_typ": offer.get("euriborTyp"),
    }


def main() -> int:
    with sync_playwright() as playwright:
        try:
            api = BrowserApi(playwright)
        except (PlaywrightError, RuntimeError) as exc:
            print(f"[ERROR] Could not open durchblicker.at in browser: {exc}", flush=True)
            return 1
        try:
            return scrape(api)
        except BlockedError as exc:
            print(f"[ERROR] Blocked by durchblicker.at, aborting run: {exc}", flush=True)
            return 1
        finally:
            api.close()


def scrape(api: BrowserApi) -> int:
    base_metadata = {
        "kreditbetrag": 500000.00,
        "kaufpreis": 500000.00,
        "kaufnebenkosten": 50000.00,
        "eigenmittel": 150000.00,
        "haushalt_alter": 45,
        "haushalt_einkommen": 8500.00,
        "haushalt_nutzflaeche": 100,
        "haushalt_kreditraten": 300.00,
    }

    print("\n" + "=" * 80)
    print("[INFO] Durchblicker Immokredit Scraper (tariff-calculate API via browser)")
    print(f"[INFO] Laufzeiten: {LAUFZEITEN_TO_SCRAPE}")
    print("=" * 80 + "\n")

    successful_runs = 0
    total_variations = 0
    failed_calls = 0
    has_valid_data = False

    for laufzeit in LAUFZEITEN_TO_SCRAPE:
        fixierung_values = get_fixierung_values_for_laufzeit(laufzeit)
        print(f"\n[INFO] Laufzeit {laufzeit} Jahre, Fixierungen: {fixierung_values}")

        variations_data = []
        for fixierung in fixierung_values:
            offer = fetch_offer(api, laufzeit, fixierung)
            variation = offer_to_variation(offer, laufzeit, fixierung)
            variations_data.append(variation)

            if offer:
                has_valid_data = True
                print(
                    f"[INFO]   Fixierung {fixierung:>2}J: Rate {variation['rate']}, "
                    f"Zinssatz {variation['zinssatz']}, "
                    f"Effektiv {variation['effektiver_zinssatz']}, "
                    f"Bank #{variation['bank_id']}, "
                    f"Euribor {variation['euribor']} ({variation['euribor_typ']}M)",
                    flush=True,
                )
            else:
                failed_calls += 1

            time.sleep(DELAY_BETWEEN_CALLS)

        if not any(v["rate"] is not None for v in variations_data):
            # Don't store an all-empty run (e.g. when blocked) - it would show
            # up as a gap of "-" rows in the trend tables.
            print(f"[ERROR] Laufzeit {laufzeit}: no valid offers, not saving", flush=True)
            continue

        run_metadata = dict(base_metadata)
        run_metadata["scrape_date"] = datetime.now()
        run_metadata["laufzeit_jahre"] = laufzeit
        run_metadata["notes"] = f"API scraper (tariff-calculate, browser) - {laufzeit} Jahre"

        try:
            run_id = save_scraping_data(
                {
                    "run_metadata": run_metadata,
                    "fixierung_variations": variations_data,
                }
            )
            print(
                f"[INFO] Run ID {run_id}: {laufzeit} Jahre, "
                f"{len(variations_data)} variations saved"
            )
            successful_runs += 1
            total_variations += len(variations_data)
        except Exception as exc:
            print(f"[ERROR] Failed to save Laufzeit {laufzeit}: {exc}", flush=True)

    print("\n" + "=" * 80)
    if has_valid_data:
        print("[INFO] Scraping complete with valid data")
    else:
        print("[ERROR] Scraping complete but NO valid data extracted")
    print(f"[INFO] Successful runs: {successful_runs}/{len(LAUFZEITEN_TO_SCRAPE)}")
    print(
        f"[INFO] Total variations: {total_variations} "
        f"(failed API calls: {failed_calls})"
    )
    print("=" * 80 + "\n")

    return 0 if has_valid_data else 1


if __name__ == "__main__":
    raise SystemExit(main())
