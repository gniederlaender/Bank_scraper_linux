#!/usr/bin/env python3
"""
SWAP and Euribor Data Fetcher Module

Fetches EUR interest rate data from multiple sources:
1. ECB API for Euribor 3M
2. Sparkasse.at for EUR SWAP rates (primary source)
3. Fallback options if primary fails

This module is integrated into generate_report.py to automatically
fetch rate data matching the mortgage loan date range.

Enhanced with smart caching that automatically detects missing data
and fetches from API when needed.
"""

import requests
import json
import re
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
from io import StringIO
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Sparkasse.at Notation IDs for EUR Interest Rate Swaps
SPARKASSE_NOTATION_IDS = {
    "5Y": "F15237121",   # EUR 5Y IRS
    "10Y": "F15237123",  # EUR 10Y IRS (confirmed)
    "15Y": "F15237559",  # EUR 15Y IRS (confirmed)
    "20Y": "F15237560",  # EUR 20Y IRS
    "25Y": "F15237561",  # EUR 25Y IRS (confirmed)
}

# German month names for output
GERMAN_MONTHS = [
    'Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
    'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'
]


class ECBDataFetcher:
    """Fetches Euribor data from ECB Statistical Data Warehouse API"""

    BASE_URL = "https://data-api.ecb.europa.eu/service/data"
    EURIBOR_3M_KEY = "FM/M.U2.EUR.RT.MM.EURIBOR3MD_.HSTA"

    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'text/csv',
            'User-Agent': 'Mozilla/5.0 Management Report Generator'
        })

    def fetch_euribor_3m(self, start_period: str, end_period: str) -> Dict[str, float]:
        """
        Fetch Euribor 3M monthly rates from ECB

        Args:
            start_period: Start date in YYYY-MM format
            end_period: End date in YYYY-MM format

        Returns:
            Dict mapping period (YYYY-MM) to rate value
        """
        url = f"{self.BASE_URL}/{self.EURIBOR_3M_KEY}"
        params = {
            "startPeriod": start_period,
            "endPeriod": end_period,
            "format": "csvdata"
        }

        logger.info(f"Fetching Euribor 3M from ECB: {start_period} to {end_period}")

        try:
            response = self.session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()

            # Parse CSV response
            rates = {}
            lines = response.text.strip().split('\n')

            # Skip header
            for line in lines[1:]:
                parts = line.split(',')
                if len(parts) >= 10:
                    # TIME_PERIOD is typically column 8, OBS_VALUE is column 9
                    time_period = parts[8] if len(parts) > 8 else None
                    obs_value = parts[9] if len(parts) > 9 else None

                    if time_period and obs_value:
                        try:
                            rates[time_period] = float(obs_value)
                        except ValueError:
                            pass

            logger.info(f"Fetched {len(rates)} Euribor rates from ECB")
            return rates

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch Euribor from ECB: {e}")
            return {}


class SparkasseFetcher:
    """Fetches SWAP rates from Sparkasse.at via their GraphQL API"""

    GRAPHQL_URL = "https://mig.erstegroup.com/gql/at-mdp/"
    CHART_URL = "https://www.sparkasse.at/investments/interactive-chart"

    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            'accept': '*/*',
            'accept-encoding': 'gzip, deflate, br, zstd',
            'accept-language': 'de,de-DE;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6,hu;q=0.5,de-AT;q=0.4',
            'content-type': 'application/json',
            'origin': 'https://www.sparkasse.at',
            'referer': 'https://www.sparkasse.at/',
            'user-agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1 Edg/144.0.0.0'
        })

    def fetch_swap_rates(self, start_date: datetime, end_date: datetime) -> Dict[str, Dict[str, float]]:
        """
        Fetch SWAP rates from Sparkasse.at

        Args:
            start_date: Start date
            end_date: End date

        Returns:
            Dict mapping period (YYYY-MM) to rates dict {"5Y": rate, "10Y": rate, ...}
        """
        logger.info(f"Fetching SWAP rates from Sparkasse: {start_date.strftime('%Y-%m')} to {end_date.strftime('%Y-%m')}")

        all_rates = {}

        for maturity, notation_id in SPARKASSE_NOTATION_IDS.items():
            try:
                rates = self._fetch_single_maturity(notation_id, start_date, end_date)

                for period, rate in rates.items():
                    if period not in all_rates:
                        all_rates[period] = {}
                    all_rates[period][maturity] = rate

                logger.info(f"Fetched {len(rates)} {maturity} SWAP rates")

            except Exception as e:
                logger.warning(f"Failed to fetch {maturity} SWAP from Sparkasse: {e}")

        return all_rates

    def _fetch_single_maturity(self, notation_id: str, start_date: datetime, end_date: datetime) -> Dict[str, float]:
        """Fetch historical data for a single SWAP maturity using GraphQL API"""
        # Use GraphQL API directly (same as working test script)
        return self._fetch_via_graphql(notation_id, start_date, end_date)

    def _parse_chart_data(self, html_content: str, start_date: datetime, end_date: datetime) -> Dict[str, float]:
        """Parse chart data from HTML content"""
        rates = {}

        # Look for JSON data in the page (common patterns)
        patterns = [
            r'"timeseries":\s*(\[[\s\S]*?\])',
            r'"data":\s*(\[[\s\S]*?\])',
            r'var\s+chartData\s*=\s*(\[[\s\S]*?\]);',
        ]

        for pattern in patterns:
            match = re.search(pattern, html_content)
            if match:
                try:
                    data = json.loads(match.group(1))
                    # Process the data
                    for item in data:
                        if isinstance(item, dict):
                            date_str = item.get('date') or item.get('x')
                            value = item.get('value') or item.get('y')
                            if date_str and value:
                                try:
                                    dt = datetime.strptime(date_str[:10], '%Y-%m-%d')
                                    period = dt.strftime('%Y-%m')
                                    rates[period] = float(value)
                                except (ValueError, TypeError):
                                    pass
                except json.JSONDecodeError:
                    pass

        return rates

    def _fetch_via_graphql(self, notation_id: str, start_date: datetime, end_date: datetime) -> Dict[str, float]:
        """Fetch data via GraphQL API using NotationTimeSeries query"""
        
        # GraphQL query matching the working test script
        graphql_query = """
query NotationTimeSeries($notationId: NotationId!, $period: TimeSeriesPeriod!, $priceType: TimeSeriesPriceType, $periodDateFrom: DateTime) {
  notationTimeSeries(
    notationId: $notationId
    period: $period
    priceType: $priceType
    periodDateFrom: $periodDateFrom
  ) {
    notationId
    priceType
    range {
      start
      end
      __typename
    }
    objects
    __typename
  }
}
"""

        # Calculate period - use P3Y_EOD for 3 years, adjust if needed
        # For date range, we'll use P3Y_EOD which gives us enough data
        period = "P3Y_EOD"
        
        # Prepare payload matching the test script format
        payload = [{
            "operationName": "NotationTimeSeries",
            "variables": {
                "period": period,
                "priceType": "MID",
                "notationId": notation_id
            },
            "extensions": {
                "queryId": "NotationTimeSeries-5127048867-6006834646-fkintn7sl4",
                "path": {
                    "ancestorOrigins": {},
                    "href": f"https://www.sparkasse.at/investments/maerkte/maerkte-im-ueberblick/geld-und-kapitalmarkt/interest-rates#{notation_id}",
                    "origin": "https://www.sparkasse.at",
                    "protocol": "https:",
                    "host": "www.sparkasse.at",
                    "hostname": "www.sparkasse.at",
                    "port": "",
                    "pathname": "/investments/maerkte/maerkte-im-ueberblick/geld-und-kapitalmarkt/interest-rates",
                    "search": "",
                    "hash": f"#{notation_id}"
                }
            },
            "query": graphql_query
        }]

        try:
            response = self.session.post(
                self.GRAPHQL_URL,
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()
            data = response.json()

            rates = {}
            # Parse the response structure from NotationTimeSeries
            if isinstance(data, list) and len(data) > 0:
                if "data" in data[0] and "notationTimeSeries" in data[0]["data"]:
                    ts_data = data[0]["data"]["notationTimeSeries"]
                    objects = ts_data.get("objects", [])
                    
                    # Aggregate daily data points to monthly averages
                    monthly_data = {}  # {YYYY-MM: [values]}
                    
                    # Calculate end of end_date month to include all days in that month
                    if end_date.month == 12:
                        end_of_month = datetime(end_date.year + 1, 1, 1)
                    else:
                        end_of_month = datetime(end_date.year, end_date.month + 1, 1)
                    
                    # Process objects: [[timestamp_ms, value], ...]
                    for item in objects:
                        if isinstance(item, list) and len(item) >= 2:
                            timestamp_ms = item[0]
                            value = item[1]
                            
                            # Convert timestamp (milliseconds) to datetime
                            dt = datetime.fromtimestamp(timestamp_ms / 1000)
                            
                            # Only include dates within our requested range
                            # Include all dates from start_date to end of end_date's month
                            if start_date <= dt < end_of_month:
                                period = dt.strftime('%Y-%m')
                                if period not in monthly_data:
                                    monthly_data[period] = []
                                monthly_data[period].append(float(value))
                    
                    # Calculate monthly averages
                    for period, values in monthly_data.items():
                        if values:
                            rates[period] = sum(values) / len(values)
            
            return rates

        except Exception as e:
            logger.warning(f"GraphQL fetch failed for {notation_id}: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.warning(f"Response status: {e.response.status_code}, body: {e.response.text[:200]}")
            return {}


class InvestingComFetcher:
    """Fallback fetcher for SWAP rates from Investing.com"""

    SWAP_URLS = {
        "5Y": "https://www.investing.com/rates-bonds/eur-5-years-irs-interest-rate-swap-historical-data",
        "10Y": "https://www.investing.com/rates-bonds/eur-10-years-irs-interest-rate-swap-historical-data",
        "15Y": "https://www.investing.com/rates-bonds/eur-15-years-irs-interest-rate-swap-historical-data",
        "20Y": "https://www.investing.com/rates-bonds/eur-20-years-irs-interest-rate-swap-historical-data",
        "25Y": "https://www.investing.com/rates-bonds/eur-25-years-irs-interest-rate-swap-historical-data",
    }

    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        })

    def fetch_swap_rates(self, start_date: datetime, end_date: datetime) -> Dict[str, Dict[str, float]]:
        """
        Fetch SWAP rates from Investing.com (fallback)

        Note: This may be rate-limited or blocked. Use as last resort.
        """
        logger.info("Attempting fallback to Investing.com for SWAP rates")

        all_rates = {}

        for maturity, url in self.SWAP_URLS.items():
            try:
                rates = self._scrape_historical_data(url, start_date, end_date)

                for period, rate in rates.items():
                    if period not in all_rates:
                        all_rates[period] = {}
                    all_rates[period][maturity] = rate

                logger.info(f"Scraped {len(rates)} {maturity} SWAP rates from Investing.com")

            except Exception as e:
                logger.warning(f"Failed to scrape {maturity} SWAP from Investing.com: {e}")

        return all_rates

    def _scrape_historical_data(self, url: str, start_date: datetime, end_date: datetime) -> Dict[str, float]:
        """Scrape historical data table from Investing.com"""

        # Note: Investing.com may require JavaScript or have anti-scraping measures
        # This is a simplified implementation that may need enhancement

        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()

            rates = {}

            # Look for data table in HTML
            # Pattern for table rows with date and price
            table_pattern = r'<tr[^>]*>[\s\S]*?<td[^>]*>([^<]+)</td>[\s\S]*?<td[^>]*>([0-9.]+)</td>'

            matches = re.findall(table_pattern, response.text)

            for date_str, price_str in matches:
                try:
                    # Parse various date formats
                    for fmt in ['%b %d, %Y', '%d/%m/%Y', '%Y-%m-%d']:
                        try:
                            dt = datetime.strptime(date_str.strip(), fmt)
                            if start_date <= dt <= end_date:
                                period = dt.strftime('%Y-%m')
                                # Take first (most recent) value for each month
                                if period not in rates:
                                    rates[period] = float(price_str)
                            break
                        except ValueError:
                            continue
                except (ValueError, TypeError):
                    pass

            return rates

        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to scrape Investing.com: {e}")
            return {}


def get_date_range_from_loans(mortgage_loans: List[Dict]) -> Tuple[datetime, datetime]:
    """
    Extract date range from mortgage loans data

    Args:
        mortgage_loans: List of mortgage loan dictionaries

    Returns:
        Tuple of (start_date, end_date)
    """
    dates = []

    for loan in mortgage_loans:
        if 'year' in loan and 'month' in loan:
            try:
                dates.append(datetime(loan['year'], loan['month'], 1))
            except (ValueError, TypeError):
                pass

    if not dates:
        # Default: current month and 12 months back
        end_date = datetime.now().replace(day=1)
        start_date = datetime(end_date.year - 1, end_date.month, 1)
        return start_date, end_date

    return min(dates), max(dates)


def load_manual_swap_rates(manual_path: Path) -> Dict[str, Dict[str, float]]:
    """
    Load SWAP rates from manual JSON file

    Args:
        manual_path: Path to swap_rates_manual.json

    Returns:
        Dict mapping period (YYYY-MM) to rates dict
    """
    try:
        with open(manual_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        logger.info(f"Loaded {len(data)} months of manual SWAP data from {manual_path}")
        return data
    except Exception as e:
        logger.warning(f"Could not load manual SWAP data: {e}")
        return {}


def save_swap_rates_to_manual(swap_rates: Dict[str, Dict[str, float]], 
                               output_path: Path) -> None:
    """
    Save SWAP rates to manual JSON file
    
    Args:
        swap_rates: Dict mapping "YYYY-MM" to dict of {maturity: rate}
        output_path: Path to output file
    """
    # Sort by date
    sorted_data = dict(sorted(swap_rates.items()))
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(sorted_data, f, indent=4, ensure_ascii=False)
    
    logger.info(f"Saved {len(sorted_data)} months of SWAP data to {output_path}")


def _get_required_periods(start_date: datetime, end_date: datetime) -> List[str]:
    """
    Generate list of required periods (YYYY-MM) for the date range
    
    Args:
        start_date: Start date
        end_date: End date
        
    Returns:
        List of period strings (YYYY-MM)
    """
    periods = []
    current = start_date.replace(day=1)
    end_of_end_month = end_date.replace(day=1)
    if end_date.month == 12:
        end_of_end_month = datetime(end_date.year + 1, 1, 1)
    else:
        end_of_end_month = datetime(end_date.year, end_date.month + 1, 1)
    
    while current < end_of_end_month:
        periods.append(current.strftime('%Y-%m'))
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)
    
    return periods


def _check_cache_coverage(cached_rates: Dict[str, Dict[str, float]], 
                          required_periods: List[str]) -> Tuple[bool, List[str]]:
    """
    Check if cached data covers all required periods
    
    Args:
        cached_rates: Cached SWAP rates dict
        required_periods: List of required period strings (YYYY-MM)
        
    Returns:
        Tuple of (is_complete, missing_periods)
    """
    cached_periods = set(cached_rates.keys())
    required_set = set(required_periods)
    missing_periods = sorted(list(required_set - cached_periods))
    
    is_complete = len(missing_periods) == 0
    
    return is_complete, missing_periods


def fetch_all_rates(start_date: datetime, end_date: datetime,
                    manual_swap_path: Optional[Path] = None,
                    force_api: bool = False) -> List[Dict[str, Any]]:
    """
    Fetch all required rates (Euribor + SWAP) for the given date range
    
    Enhanced with smart caching that automatically detects missing data
    and fetches from API when needed.

    Args:
        start_date: Start date
        end_date: End date
        manual_swap_path: Optional path to manual SWAP rates JSON
        force_api: If True, force fetching from API and update manual file

    Returns:
        List of monthly rate data in swap_data.js format
    """
    start_period = start_date.strftime('%Y-%m')
    end_period = end_date.strftime('%Y-%m')

    logger.info(f"Fetching rates from {start_period} to {end_period}")

    # Fetch Euribor from ECB (always fresh, no caching)
    ecb_fetcher = ECBDataFetcher()
    euribor_rates = ecb_fetcher.fetch_euribor_3m(start_period, end_period)

    # Fetch SWAP rates - try multiple sources with fallbacks and smart caching
    swap_rates = {}

    # Determine manual file path
    if manual_swap_path is None:
        # Look for default location - check code directory first, then parent
        script_dir = Path(__file__).parent
        manual_swap_path = script_dir / 'swap_rates_manual.json'
        if not manual_swap_path.exists():
            # Try parent directory (root of project)
            manual_swap_path = script_dir.parent / 'swap_rates_manual.json'

    # Smart caching logic
    cached_swap_rates = {}
    needs_fetch = False
    
    if not force_api and manual_swap_path.exists():
        # Load cached data
        cached_swap_rates = load_manual_swap_rates(manual_swap_path)
        
        if cached_swap_rates:
            # Check if cache covers required date range
            required_periods = _get_required_periods(start_date, end_date)
            is_complete, missing_periods = _check_cache_coverage(cached_swap_rates, required_periods)
            
            if is_complete:
                logger.info(f"Cache is complete - using cached SWAP data for {len(required_periods)} periods")
                swap_rates = cached_swap_rates
            else:
                logger.info(f"Cache is incomplete - missing {len(missing_periods)} periods: {missing_periods}")
                needs_fetch = True
                # Use cached data as starting point
                swap_rates = cached_swap_rates.copy()
        else:
            logger.info("Cache file exists but is empty - fetching from API...")
            needs_fetch = True
    else:
        if force_api:
            logger.info("Force API flag set - fetching fresh data from API...")
        else:
            logger.info("No cache file found - fetching from API...")
        needs_fetch = True

    # Fetch missing data from API if needed
    if needs_fetch:
        try:
            logger.info("Fetching SWAP rates from Sparkasse API...")
            sparkasse_fetcher = SparkasseFetcher()
            fetched_rates = sparkasse_fetcher.fetch_swap_rates(start_date, end_date)
            
            if fetched_rates:
                # Merge fetched data with cached data (fetched data takes precedence)
                swap_rates.update(fetched_rates)
                logger.info(f"Merged {len(fetched_rates)} periods from API with cache")
            else:
                # If Sparkasse fails, try Investing.com
                logger.info("Sparkasse fetch failed, trying Investing.com fallback...")
                investing_fetcher = InvestingComFetcher()
                fetched_rates = investing_fetcher.fetch_swap_rates(start_date, end_date)
                
                if fetched_rates:
                    swap_rates.update(fetched_rates)
                    logger.info(f"Merged {len(fetched_rates)} periods from Investing.com with cache")
        except Exception as e:
            logger.warning(f"Failed to fetch SWAP rates from API: {e}")
            logger.info("Using cached data (may have gaps)")
        
        # Update cache file with merged data
        if swap_rates:
            logger.info(f"Saving merged SWAP data to {manual_swap_path}")
            save_swap_rates_to_manual(swap_rates, manual_swap_path)

    # Combine into output format
    result = []

    current = start_date.replace(day=1)
    while current <= end_date:
        period = current.strftime('%Y-%m')

        month_data = {
            "year": current.year,
            "month": current.month,
            "monthName": f"{GERMAN_MONTHS[current.month - 1]} {current.year}",
            "rates": {}
        }

        # Add Euribor 3M
        if period in euribor_rates:
            month_data["rates"]["3M"] = round(euribor_rates[period], 2)

        # Add SWAP rates
        if period in swap_rates:
            for maturity, rate in swap_rates[period].items():
                month_data["rates"][maturity] = round(rate, 2)

        # Only add if we have at least some data
        if month_data["rates"]:
            result.append(month_data)
        else:
            # Add placeholder with warning
            logger.warning(f"No rate data available for {period}")

        # Move to next month
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)

    return result


def generate_swap_data_js(data: List[Dict], output_path: Path) -> None:
    """
    Generate swap_data.js file from fetched data

    Args:
        data: List of monthly rate data
        output_path: Path to output swap_data.js file
    """
    # Format data as JavaScript
    data_json = json.dumps(data, ensure_ascii=False, indent=4)

    js_content = f'''// EUR SWAP Rates Data
// Historical EUR Interest Rate Swap rates for Hauptfixlaufzeiten
// Data represents mid-market rates for major maturities
//
// AUTO-GENERATED by swap_data_fetcher.py - Do not edit manually
// Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
//
// Data Sources:
// - Euribor 3M: ECB Statistical Data Warehouse
// - SWAP rates: Sparkasse.at / Erste Group (FactSet)
//
// Date Range: {data[0]["monthName"] if data else "N/A"} - {data[-1]["monthName"] if data else "N/A"}

const eurSwapRates = {data_json};
'''

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(js_content)

    logger.info(f"Generated swap_data.js: {output_path}")
    logger.info(f"Contains {len(data)} months of data")


# CLI interface for standalone testing
if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description='Fetch SWAP and Euribor rates')
    parser.add_argument('--start', type=str, required=True, help='Start date (YYYY-MM)')
    parser.add_argument('--end', type=str, required=True, help='End date (YYYY-MM)')
    parser.add_argument('--output', type=str, default='swap_data.js', help='Output file path')

    args = parser.parse_args()

    start_date = datetime.strptime(args.start, "%Y-%m")
    end_date = datetime.strptime(args.end, "%Y-%m")

    data = fetch_all_rates(start_date, end_date)

    if data:
        generate_swap_data_js(data, Path(args.output))
        print(f"\nSuccessfully generated {args.output}")
    else:
        print("\nFailed to fetch rate data")
        sys.exit(1)

