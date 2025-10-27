#!/usr/bin/env python3
"""
Austrian Bank Scraper - Refactored Version
A modular, extensible system for scraping Austrian bank interest rates
"""

import os
import re
import json
import time
import signal
import sqlite3
import logging
import smtplib
import requests
import pandas as pd
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import glob
import xml.etree.ElementTree as ET

from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from fake_useragent import UserAgent
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scraper.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class LoanData:
    """Data class for loan information"""
    bank_name: str
    product_name: str
    sollzinssatz: Optional[str] = None
    effektiver_jahreszins: Optional[str] = None
    nettokreditbetrag: Optional[str] = None
    vertragslaufzeit: Optional[str] = None
    gesamtbetrag: Optional[str] = None
    monatliche_rate: Optional[str] = None
    min_betrag: Optional[str] = None
    max_betrag: Optional[str] = None
    min_laufzeit: Optional[str] = None
    max_laufzeit: Optional[str] = None
    currency: str = 'EUR'
    source_url: Optional[str] = None
    raw_data: Optional[str] = None
    date_scraped: Optional[datetime] = None

    # Additional fields for Bank Austria API data
    bearbeitungsspesen: Optional[str] = None  # Processing fees
    schatzgebuhr: Optional[str] = None  # Estimate fee
    eintragungsgebuhr: Optional[str] = None  # Entry fee
    risikovorsorge: Optional[str] = None  # Risk provision
    kontofuhrung_viertel: Optional[str] = None  # Account management quarterly
    sicherheitsfaktor: Optional[str] = None  # Security factor
    rate_kontofuhrung: Optional[str] = None  # Rate with account management
    payments_total: Optional[str] = None  # Total payments
    
    # Parameter fields
    account_fee_monthly: Optional[str] = None  # Monthly account fee
    processing_fee_perc: Optional[str] = None  # Processing fee percentage
    security_factor_perc: Optional[str] = None  # Security factor percentage
    estimate_fee: Optional[str] = None  # Estimate fee
    estimate_fee_perc: Optional[str] = None  # Estimate fee percentage
    entry_fee_perc: Optional[str] = None  # Entry fee percentage
    risk_fee_perc: Optional[str] = None  # Risk fee percentage
    
    # Erste Bank (Sparkasse) specific fields
    installment_fixed: Optional[str] = None  # Fixed installment amount
    installment_internal: Optional[str] = None  # Internal installment amount
    fixed_interest_rate: Optional[str] = None  # Fixed interest rate (first phase)
    variable_interest_rate: Optional[str] = None  # Variable interest rate (second phase)
    fixed_phase_months: Optional[str] = None  # Number of months in fixed phase
    variable_phase_months: Optional[str] = None  # Number of months in variable phase
    brokerage_fee_perc: Optional[str] = None  # Brokerage fee percentage
    account_management_quarterly: Optional[str] = None  # Account management fee per quarter
    equity_procurement_fee_perc: Optional[str] = None  # Equity procurement fee percentage
    entry_fee_perc_erste: Optional[str] = None  # Entry fee percentage (Erste Bank)
    authentication_costs: Optional[str] = None  # Authentication costs
    product_type: Optional[str] = None  # Type of loan product
    requirements: Optional[str] = None  # Loan requirements
    calculation_date: Optional[str] = None  # Date of calculation

    def __post_init__(self):
        if self.date_scraped is None:
            self.date_scraped = datetime.now()


class TimeoutError(Exception):
    """Custom timeout exception"""
    pass


def timeout_handler(signum, frame):
    """Signal handler for timeout"""
    raise TimeoutError("Operation timed out")


class WebDriverManager:
    """Manages WebDriver setup and lifecycle"""
    
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.driver = None
        self.wait = None
        self.ua = UserAgent()
        
    def setup_driver(self) -> webdriver.Firefox:
        """Set up Firefox WebDriver with appropriate options"""
        os.environ['MOZ_HEADLESS'] = '1'
        os.environ['MOZ_DISABLE_CONTENT_SANDBOX'] = '1'
        
        options = Options()
        options.add_argument('--headless')
        options.set_preference('general.useragent.override', self.ua.random)
        
        service = Service(
            executable_path='/usr/local/bin/geckodriver',
            log_output='geckodriver.log'
        )
        
        logger.info("Creating Firefox driver...")
        
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(self.timeout)
        
        try:
            self.driver = webdriver.Firefox(service=service, options=options)
            signal.alarm(0)
            logger.info("Firefox driver created successfully!")
            self.wait = WebDriverWait(self.driver, 10)
            return self.driver
        except TimeoutError:
            logger.error("Timeout: Firefox took too long to start")
            raise
        except Exception as e:
            signal.alarm(0)
            logger.error(f"Error creating Firefox driver: {e}")
            raise
    
    def quit_driver(self):
        """Quit the WebDriver"""
        if self.driver:
            self.driver.quit()
            self.driver = None
            self.wait = None


class DatabaseManager:
    """Handles all database operations"""
    
    def __init__(self, db_path: str = 'austrian_banks_housing_loan.db'):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize SQLite database and create necessary tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS interest_rates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bank_name TEXT,
                product_name TEXT,
                rate TEXT,
                currency TEXT,
                date_scraped TIMESTAMP,
                source_url TEXT,
                nettokreditbetrag TEXT,
                gesamtbetrag TEXT,
                vertragslaufzeit TEXT,
                effektiver_jahreszins TEXT,
                monatliche_rate TEXT,
                min_betrag TEXT,
                max_betrag TEXT,
                min_laufzeit TEXT,
                max_laufzeit TEXT,
                full_text TEXT,
                -- Additional fields for Bank Austria API data
                bearbeitungsspesen TEXT,
                schatzgebuhr TEXT,
                eintragungsgebuhr TEXT,
                risikovorsorge TEXT,
                kontofuhrung_viertel TEXT,
                sicherheitsfaktor TEXT,
                rate_kontofuhrung TEXT,
                payments_total TEXT,
                -- Parameter fields
                account_fee_monthly TEXT,
                processing_fee_perc TEXT,
                security_factor_perc TEXT,
                estimate_fee TEXT,
                estimate_fee_perc TEXT,
                entry_fee_perc TEXT,
                risk_fee_perc TEXT,
                -- Erste Bank (Sparkasse) specific fields
                installment_fixed TEXT,
                installment_internal TEXT,
                fixed_interest_rate TEXT,
                variable_interest_rate TEXT,
                fixed_phase_months TEXT,
                variable_phase_months TEXT,
                brokerage_fee_perc TEXT,
                account_management_quarterly TEXT,
                equity_procurement_fee_perc TEXT,
                entry_fee_perc_erste TEXT,
                authentication_costs TEXT,
                product_type TEXT,
                requirements TEXT,
                calculation_date TEXT
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def store_loan_data(self, loan_data: LoanData):
        """Store loan data in database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO interest_rates (
                bank_name, product_name, rate, currency, date_scraped, source_url,
                nettokreditbetrag, gesamtbetrag, vertragslaufzeit, effektiver_jahreszins,
                monatliche_rate, min_betrag, max_betrag, min_laufzeit, max_laufzeit, full_text,
                bearbeitungsspesen, schatzgebuhr, eintragungsgebuhr, risikovorsorge,
                kontofuhrung_viertel, sicherheitsfaktor, rate_kontofuhrung, payments_total,
                account_fee_monthly, processing_fee_perc, security_factor_perc, estimate_fee,
                estimate_fee_perc, entry_fee_perc, risk_fee_perc,
                installment_fixed, installment_internal, fixed_interest_rate, variable_interest_rate,
                fixed_phase_months, variable_phase_months, brokerage_fee_perc, account_management_quarterly,
                equity_procurement_fee_perc, entry_fee_perc_erste, authentication_costs, product_type,
                requirements, calculation_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            loan_data.bank_name, loan_data.product_name, loan_data.sollzinssatz,
            loan_data.currency, loan_data.date_scraped, loan_data.source_url,
            loan_data.nettokreditbetrag, loan_data.gesamtbetrag, loan_data.vertragslaufzeit,
            loan_data.effektiver_jahreszins, loan_data.monatliche_rate, loan_data.min_betrag,
            loan_data.max_betrag, loan_data.min_laufzeit, loan_data.max_laufzeit, loan_data.raw_data,
            loan_data.bearbeitungsspesen, loan_data.schatzgebuhr, loan_data.eintragungsgebuhr,
            loan_data.risikovorsorge, loan_data.kontofuhrung_viertel, loan_data.sicherheitsfaktor,
            loan_data.rate_kontofuhrung, loan_data.payments_total, loan_data.account_fee_monthly,
            loan_data.processing_fee_perc, loan_data.security_factor_perc, loan_data.estimate_fee,
            loan_data.estimate_fee_perc, loan_data.entry_fee_perc, loan_data.risk_fee_perc,
            loan_data.installment_fixed, loan_data.installment_internal, loan_data.fixed_interest_rate,
            loan_data.variable_interest_rate, loan_data.fixed_phase_months, loan_data.variable_phase_months,
            loan_data.brokerage_fee_perc, loan_data.account_management_quarterly, loan_data.equity_procurement_fee_perc,
            loan_data.entry_fee_perc_erste, loan_data.authentication_costs, loan_data.product_type,
            loan_data.requirements, loan_data.calculation_date
        ))
        
        conn.commit()
        conn.close()
    
    def get_latest_data(self) -> List[Dict]:
        """Get the latest data for each bank"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            WITH latest_entries AS (
                SELECT bank_name, MAX(date_scraped) as latest_date
                FROM interest_rates
                GROUP BY bank_name
            )
            SELECT i.*
            FROM interest_rates i
            INNER JOIN latest_entries le 
            ON i.bank_name = le.bank_name 
            AND i.date_scraped = le.latest_date
            ORDER BY i.bank_name
        ''')
        
        rows = cursor.fetchall()
        column_names = [description[0] for description in cursor.description]
        
        result = []
        for row in rows:
            result.append(dict(zip(column_names, row)))
        
        conn.close()
        return result
    
    def export_to_excel(self, filename: str = 'austrian_banks_data_housing_loan.xlsx'):
        """Export all data to Excel file"""
        try:
            conn = sqlite3.connect(self.db_path)
            interest_rates_df = pd.read_sql_query("SELECT * FROM interest_rates", conn)
            
            with pd.ExcelWriter(filename) as writer:
                interest_rates_df.to_excel(writer, sheet_name='Interest Rates', index=False)
            
            logger.info(f"Data exported to {filename} successfully")
            conn.close()
        except Exception as e:
            logger.error(f"Error exporting to Excel: {str(e)}")
            if 'conn' in locals():
                conn.close()


class BaseBankScraper(ABC):
    """Abstract base class for bank scrapers"""
    
    def __init__(self, driver_manager: WebDriverManager):
        self.driver_manager = driver_manager
        self.driver = driver_manager.driver
        self.wait = driver_manager.wait
        self.bank_name = self.get_bank_name()
        self.base_url = self.get_base_url()
        
    @abstractmethod
    def get_bank_name(self) -> str:
        """Return the bank name"""
        pass
    
    @abstractmethod
    def get_base_url(self) -> str:
        """Return the base URL for scraping"""
        pass
    
    @abstractmethod
    def scrape_loan_data(self, loan_amount: int = 10000, duration_months: int = 60) -> LoanData:
        """Scrape loan data from the bank's website"""
        pass
    
    def take_screenshot(self, filename: str = None):
        """Take a screenshot for debugging"""
        if filename is None:
            filename = f"{self.bank_name}_screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        
        try:
            self.driver.save_screenshot(f"screenshots/{filename}")
            logger.info(f"Screenshot saved: {filename}")
        except Exception as e:
            logger.error(f"Error taking screenshot: {e}")


class RaiffeisenScraper(BaseBankScraper):
    """Scraper for Raiffeisen Bank"""
    
    def get_bank_name(self) -> str:
        return 'raiffeisen'
    
    def get_base_url(self) -> str:
        return 'https://www.raiffeisen.at/noew/rlb/de/privatkunden/kredit-leasing/der-faire-credit.html'
    
    def scrape_loan_data(self, loan_amount: int = 10000, duration_months: int = 60) -> LoanData:
        """Scrape Raiffeisen loan data"""
        logger.info(f"Scraping {self.bank_name} loan data")
        
        self.driver.get(self.base_url)
        time.sleep(10)  # Wait for page to load
        
        # Find the representative calculation element
        selectors = [
            '.credit-calculator-dfc-representative-calc',
            '[class*="representative-calc"]',
            '[class*="credit-calculator"]'
        ]
        
        element = None
        for selector in selectors:
            try:
                element = self.wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                if element:
                    logger.info(f"Found element with selector: {selector}")
                    break
            except:
                continue
        
        if not element:
            raise Exception("Could not find the representative calculation element")
        
        text = element.text
        logger.info(f"Extracted text: {text}")
        
        # Parse the text to extract fields
        loan_data = LoanData(
            bank_name=self.bank_name,
            product_name='Representative Example',
            source_url=self.base_url,
            raw_data=text
        )
        
        # Extract data using regex
        loan_data.sollzinssatz = self._extract_with_regex(r"Sollzinssatz: ([\d,]+ %)", text)
        loan_data.effektiver_jahreszins = self._extract_with_regex(r"effektiver Jahreszins: ([\d,]+ %)", text)
        loan_data.nettokreditbetrag = self._extract_with_regex(r"Nettokreditbetrag: ([\d,.]+ Euro)", text)
        loan_data.vertragslaufzeit = self._extract_with_regex(r"Vertragslaufzeit: ([\d]+ Monate)", text)
        loan_data.gesamtbetrag = self._extract_with_regex(r"Gesamtbetrag: ([\d,.]+ Euro)", text)
        loan_data.monatliche_rate = self._extract_with_regex(r"monatliche Rate: ([\d,.]+ Euro)", text)
        
        # Extract min/max values
        self._extract_min_max_values(loan_data, text)
        
        self.take_screenshot()
        return loan_data
    
    def _extract_with_regex(self, pattern: str, text: str) -> Optional[str]:
        """Extract value using regex pattern"""
        match = re.search(pattern, text)
        return match.group(1) if match else None
    
    def _extract_min_max_values(self, loan_data: LoanData, text: str):
        """Extract min/max amount and duration from text"""
        try:
            produktangaben_match = re.search(r'Produktangaben:(.*)', text)
            if produktangaben_match:
                produktangaben = produktangaben_match.group(1)
                
                # Extract amount range
                betrag_match = re.search(r'Nettokreditbetrag: ([\d\.]+)\s*-\s*([\d\.]+) Euro', produktangaben)
                if betrag_match:
                    loan_data.min_betrag = betrag_match.group(1).replace('.', '')
                    loan_data.max_betrag = betrag_match.group(2).replace('.', '')
                
                # Extract duration range
                laufzeit_match = re.search(r'Vertragslaufzeit: (\d+)\s*-\s*(\d+) Monate', produktangaben)
                if laufzeit_match:
                    loan_data.min_laufzeit = laufzeit_match.group(1)
                    loan_data.max_laufzeit = laufzeit_match.group(2)
        except Exception as e:
            logger.warning(f"Could not parse min/max values for {self.bank_name}: {e}")


class Bank99Scraper(BaseBankScraper):
    """API-only scraper for Bank99 Housing Loans - no browser automation needed"""
    
    def get_bank_name(self) -> str:
        return 'bank99'
    
    def get_base_url(self) -> str:
        return 'https://pwa.bank99.at/public-web-api/baufirechner-kauf'
    
    def scrape_loan_data(self, loan_amount: int = 300000, duration_months: int = 300) -> LoanData:
        """Get Bank99 housing loan data via API only"""
        logger.info(f"Getting {self.bank_name} housing loan data via API (no browser needed)")
        
        # Initialize loan data
        loan_data = LoanData(
            bank_name=self.bank_name,
            product_name='Wohnkredit',
            source_url=self.get_base_url()
        )
        
        try:
            # Make direct API call
            api_data = self._make_api_call(loan_amount, duration_months)
            
            if api_data:
                self._extract_api_data(loan_data, api_data, loan_amount, duration_months)
                logger.info("✅ Bank99 API data extracted successfully")
            else:
                logger.error("API call failed or returned empty response")
                self._set_fallback_data(loan_data, loan_amount, duration_months)
                
        except Exception as e:
            logger.error(f"Error calling Bank99 API: {e}")
            self._set_fallback_data(loan_data, loan_amount, duration_months)
        
        return loan_data
    
    def _make_api_call(self, loan_amount: int, duration_months: int):
        """Make API call to Bank99 housing loan calculator"""
        # Convert months to years for API
        duration_years = duration_months // 12
        
        # Calculate equity (20% of loan amount as typical requirement)
        equity_amount = int(loan_amount * 0.2)
        
        # Set interest rate binding period (typically 10-15 years)
        interest_binding_period = min(15, duration_years)
        
        api_url = "https://pwa.bank99.at/public-web-api/baufirechner-kauf"
        
        params = {
            'kaufpreis': loan_amount,
            'eigenmittel': equity_amount,
            'produkt': 'F',  # Fixed product type
            'laufzeit': duration_years,
            'zinsbindungsFrist': interest_binding_period
        }
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'de-DE,de;q=0.9,en;q=0.8',
            'Referer': 'https://www.bank99.at/wohnfinanzierung/wohnkredit99'
        }
        
        try:
            response = requests.get(api_url, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            
            # Parse XML response
            root = ET.fromstring(response.text)
            return root
            
        except Exception as e:
            logger.error(f"API request failed: {e}")
            return None
    
    def _extract_api_data(self, loan_data: LoanData, root, loan_amount: int, duration_months: int):
        """Extract loan data from XML API response"""
        try:
            # Extract basic loan information
            loan_data.nettokreditbetrag = f"{float(root.find('finanzierungsbetrag').text):,.2f} Euro"
            loan_data.gesamtbetrag = f"{float(root.find('zuZahlenderGesamtbetrag').text):,.2f} Euro"
            loan_data.vertragslaufzeit = f"{duration_months} Monate"
            loan_data.monatliche_rate = f"{float(root.find('rate').text):,.2f} Euro"
            
            # Extract interest rates
            initial_rate = float(root.find('anfangsSollZinssatz').text)
            follow_up_rate = float(root.find('anschlussSollZinssatz').text)
            effective_rate = float(root.find('effektivZinssatz').text)
            
            loan_data.sollzinssatz = f"{initial_rate:.2f}% p.a."
            loan_data.effektiver_jahreszins = f"{effective_rate:.2f}% p.a."
            
            # Extract additional information
            purchase_price = float(root.find('kaufpreis').text)
            equity = float(root.find('eigenmittel').text)
            financing_amount = float(root.find('finanzierungsbetrag').text)
            
            # Set min/max values (static for Bank99 housing loans)
            loan_data.min_betrag = "50000"
            loan_data.max_betrag = "3000000"
            loan_data.min_laufzeit = "120"  # 10 years
            loan_data.max_laufzeit = "420"  # 35 years
            
            # Store raw API data
            loan_data.raw_data = ET.tostring(root, encoding='unicode')
            
            # Set product type and requirements
            loan_data.product_type = "Wohnkredit mit Hypothek"
            loan_data.requirements = "Eigenmittel von mindestens 20% erforderlich"
            
            logger.info(f"Bank99: Purchase price: {purchase_price:,.2f} EUR, Equity: {equity:,.2f} EUR, Financing: {financing_amount:,.2f} EUR")
            
        except Exception as e:
            logger.error(f"Error extracting API data: {e}")
    
    def _set_fallback_data(self, loan_data: LoanData, loan_amount: int, duration_months: int):
        """Set fallback data when API fails"""
        loan_data.nettokreditbetrag = f"{loan_amount:,} Euro"
        loan_data.sollzinssatz = "3.50% p.a."
        loan_data.effektiver_jahreszins = "3.76% p.a."
        loan_data.vertragslaufzeit = f"{duration_months} Monate"
        loan_data.min_betrag = "50000"
        loan_data.max_betrag = "3000000"
        loan_data.raw_data = "API call failed - using fallback data"


class ErsteScraper(BaseBankScraper):
    """API-only scraper for Erste Bank (Sparkasse) - no browser automation needed"""
    
    def get_bank_name(self) -> str:
        return 'erste'
    
    def get_base_url(self) -> str:
        return 'https://rechner.sparkasse.at/api/v2/Loan/CalculateLoanRate'
    
    def scrape_loan_data(self, loan_amount: int = 300000, duration_months: int = 300) -> LoanData:
        """Get Erste Bank housing loan data via API only"""
        logger.info(f"Getting {self.bank_name} housing loan data via API (no browser needed)")
        
        # Initialize loan data
        loan_data = LoanData(
            bank_name=self.bank_name,
            product_name='Bauspardarlehen mit Hypothek',
            source_url=self.get_base_url()
        )
        
        try:
            # Make direct API call
            api_data = self._make_api_call(loan_amount, duration_months)
            
            if api_data and len(api_data) > 0:
                self._extract_api_data(loan_data, api_data[0], loan_amount, duration_months)
                logger.info("✅ Erste Bank API data extracted successfully")
            else:
                logger.error("API call failed or returned empty response")
                self._set_fallback_data(loan_data, loan_amount, duration_months)
                
        except Exception as e:
            logger.error(f"Error calling Erste Bank API: {e}")
            self._set_fallback_data(loan_data, loan_amount, duration_months)
        
        return loan_data
    
    def _make_api_call(self, loan_amount: int, duration_months: int):
        """Make API call to Erste Bank calculator"""
        api_url = "https://rechner.sparkasse.at/api/v2/Loan/CalculateLoanRate"
        
        params = {
            'darlehenssumme': loan_amount,
            'laufzeitGesamt': duration_months,
            'mandant': 0
        }
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'de-DE,de;q=0.9,en;q=0.8',
            'Referer': 'https://rechner.sparkasse.at/',
            'Origin': 'https://rechner.sparkasse.at'
        }
        
        try:
            response = requests.get(api_url, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"API request failed: {e}")
            return None
    
    def _extract_api_data(self, loan_data: LoanData, api_data: dict, loan_amount: int, duration_months: int):
        """Extract loan data from API response"""
        import re
        
        # Map basic API data
        loan_data.monatliche_rate = f"{api_data.get('InstallmentAmount', 0):,.2f} Euro"
        loan_data.installment_fixed = f"{api_data.get('InstallmentFixed', 0):,.2f} Euro"
        loan_data.installment_internal = f"{api_data.get('InstallmentInternal', 0):,.2f} Euro"
        loan_data.vertragslaufzeit = f"{duration_months} Monate"
        
        # Parse Legend field for detailed information
        legend = api_data.get('Legend', '')
        if legend:
            loan_data.raw_data = legend
            
            # Extract effective interest rate
            eff_zins_match = re.search(r'EFFEKTIVZINSSATZ\s+(\d+,\d+)\s*%', legend)
            if eff_zins_match:
                loan_data.effektiver_jahreszins = f"{eff_zins_match.group(1)}% p.a."
            else:
                # Try alternative pattern
                eff_zins_match2 = re.search(r'EFFEKTIVZINSSATZ\s+(\d+\.\d+)\s*%', legend)
                if eff_zins_match2:
                    loan_data.effektiver_jahreszins = f"{eff_zins_match2.group(1)}% p.a."
            
            # Extract total amount
            total_match = re.search(r'ZU ZAHLENDER GESAMTBETRAG\s+([\d.,]+)\s*Euro', legend)
            if total_match:
                loan_data.gesamtbetrag = f"{total_match.group(1)} Euro"
            
            # Extract fixed interest rate
            fixed_zins_match = re.search(r'(\d+,\d+)\s*%\s*p\.a\.\s*der\s*Darlehenssumme\s*fix', legend)
            if fixed_zins_match:
                loan_data.fixed_interest_rate = f"{fixed_zins_match.group(1)}% p.a."
                loan_data.sollzinssatz = f"{fixed_zins_match.group(1)}% p.a."
            
            # Extract variable interest rate
            var_zins_match = re.search(r'variable\s*Verzinsung\s*von\s*(\d+,\d+)\s*%\s*p\.a\.', legend)
            if var_zins_match:
                loan_data.variable_interest_rate = f"{var_zins_match.group(1)}% p.a."
            
            # Extract payment phases
            fixed_phase_match = re.search(r'(\d+)\s*monatliche\s*Raten\s*in\s*der\s*Fix-Zinsphase', legend)
            if fixed_phase_match:
                loan_data.fixed_phase_months = fixed_phase_match.group(1)
            
            var_phase_match = re.search(r'(\d+)\s*monatliche\s*Raten\s*in\s*der\s*variablen\s*Phase', legend)
            if var_phase_match:
                loan_data.variable_phase_months = var_phase_match.group(1)
            
            # Extract fees
            brokerage_match = re.search(r'Vermittlungsentgelt:\s*(\d+)\s*%\s*der\s*Darlehenssumme', legend)
            if brokerage_match:
                loan_data.brokerage_fee_perc = f"{brokerage_match.group(1)}%"
            
            account_match = re.search(r'Kontoführungsgebühr:\s*([\d.,]+)\s*Euro\s*pro\s*Quartal', legend)
            if account_match:
                loan_data.account_management_quarterly = f"{account_match.group(1)} Euro"
            
            equity_match = re.search(r'Eigenmittelbeschaffungsgebühr:\s*(\d+,\d+)\s*%\s*der\s*Darlehenssumme', legend)
            if equity_match:
                loan_data.equity_procurement_fee_perc = f"{equity_match.group(1)}%"
            
            entry_match = re.search(r'Eintragungsgebühr\s*in\s*Höhe\s*von\s*(\d+,\d+)%', legend)
            if entry_match:
                loan_data.entry_fee_perc_erste = f"{entry_match.group(1)}%"
            
            # Extract product type and requirements
            product_match = re.search(r'FINANZIERUNGSFORM<br>([^<]+)', legend)
            if product_match:
                loan_data.product_type = product_match.group(1).strip()
            
            # Extract calculation date
            date_match = re.search(r'STAND<br>(\d{2}\.\d{2}\.\d{4})', legend)
            if date_match:
                loan_data.calculation_date = date_match.group(1)
            
            # Set requirements
            loan_data.requirements = "Bausparvertrag und Feuerversicherung erforderlich"
        
        # Set min/max values (static for Erste Bank)
        loan_data.min_betrag = "50000"
        loan_data.max_betrag = "2000000"
        loan_data.min_laufzeit = "60"  # 5 years
        loan_data.max_laufzeit = "420"  # 35 years
        
        # Set net credit amount (same as loan amount for this product)
        loan_data.nettokreditbetrag = f"{loan_amount:,} Euro"
    
    def _set_fallback_data(self, loan_data: LoanData, loan_amount: int, duration_months: int):
        """Set fallback data when API fails"""
        loan_data.nettokreditbetrag = f"{loan_amount:,} Euro"
        loan_data.monatliche_rate = "1,590.74 Euro"
        loan_data.sollzinssatz = "3.65% p.a."
        loan_data.effektiver_jahreszins = "4.3% p.a."
        loan_data.vertragslaufzeit = f"{duration_months} Monate"
        loan_data.min_betrag = "50000"
        loan_data.max_betrag = "2000000"
        loan_data.raw_data = "API call failed - using fallback data"


class BankAustriaScraper(BaseBankScraper):
    """API-only scraper for Bank Austria - no browser automation needed"""
    
    def get_bank_name(self) -> str:
        return 'bankaustria'
    
    def get_base_url(self) -> str:
        return 'https://rechner.bankaustria.at/api/calculate-rate/'
    
    def scrape_loan_data(self, loan_amount: int = 300000, duration_months: int = 60) -> LoanData:
        """Get Bank Austria housing loan data via API only"""
        logger.info(f"Getting {self.bank_name} housing loan data via API (no browser needed)")
        
        # Convert months to years for API
        duration_years = duration_months // 12
        
        # Initialize loan data
        loan_data = LoanData(
            bank_name=self.bank_name,
            product_name='WohnKredit',
            source_url=self.get_base_url()
        )
        
        try:
            # Make direct API call
            api_data = self._make_api_call(loan_amount, duration_years)
            
            if api_data and api_data.get('status') == 'success':
                self._extract_api_data(loan_data, api_data, loan_amount, duration_months)
                logger.info("✅ Bank Austria API data extracted successfully")
            else:
                logger.error("API call failed or returned error status")
                self._set_fallback_data(loan_data, loan_amount, duration_months)
                
        except Exception as e:
            logger.error(f"Error calling Bank Austria API: {e}")
            self._set_fallback_data(loan_data, loan_amount, duration_months)
        
        return loan_data
    
    def _make_api_call(self, loan_amount: int, duration_years: int):
        """Make API call to Bank Austria calculator"""
        api_url = "https://rechner.bankaustria.at/api/calculate-rate/"
        
        params = {
            'credit_value': loan_amount,
            'retention': duration_years,
            'interest_rate': 3,
            'riskFeePerc': 0.0,
            'typ': 1,
            'accountFeeMonthly': 7.13,
            'processingFeePerc': 1.25,
            'new': 1,
            'estimateFeePerc': '',
            'estimateFee': 572.40,
            'entryFeePerc': 1.20
        }
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'de-DE,de;q=0.9,en;q=0.8',
            'Referer': 'https://www.bankaustria.at/privatkunden-finanzierungen-und-kredite-wohnkredit.jsp'
        }
        
        try:
            response = requests.get(api_url, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"API request failed: {e}")
            return None
    
    def _extract_api_data(self, loan_data: LoanData, api_data: dict, loan_amount: int, duration_months: int):
        """Extract loan data from API response"""
        data = api_data.get('data', {})
        params = api_data.get('params', {})
        
        # Map API data to loan data fields (existing)
        loan_data.nettokreditbetrag = f"{data.get('Auszahlungsbetrag', 0):,.2f} Euro"
        loan_data.monatliche_rate = f"{data.get('Rate', 0):,.2f} Euro"
        loan_data.sollzinssatz = f"{data.get('Sollzinssatz', 0)}% p.a."
        loan_data.effektiver_jahreszins = f"{data.get('Effektivzinssatz', 0)}% p.a."
        loan_data.gesamtbetrag = f"{data.get('Gesamtkreditbetrag', 0):,.2f} Euro"
        loan_data.vertragslaufzeit = f"{duration_months} Monate"
        
        # Extract additional Bank Austria API data fields
        loan_data.bearbeitungsspesen = f"{data.get('Bearbeitungsspesen', 0):,.2f} Euro"
        loan_data.schatzgebuhr = f"{data.get('Schatzgebuhr', 0):,.2f} Euro"
        loan_data.eintragungsgebuhr = f"{data.get('Eintragungsgebuhr', 0):,.2f} Euro"
        loan_data.risikovorsorge = f"{data.get('Risikovorsorge', 0):,.2f} Euro"
        loan_data.kontofuhrung_viertel = f"{data.get('KontofuhrungViertel', 0):,.2f} Euro"
        loan_data.sicherheitsfaktor = f"{data.get('Sicherheitsfaktor', 0):.1%}"
        loan_data.rate_kontofuhrung = f"{data.get('RateKontofuhrung', 0):,.2f} Euro"
        loan_data.payments_total = str(data.get('paymentsTotal', 0))
        
        # Extract parameter fields
        loan_data.account_fee_monthly = f"{params.get('accountFeeMonthly', 0):,.2f} Euro"
        loan_data.processing_fee_perc = f"{params.get('processingFeePerc', 0):.2%}"
        loan_data.security_factor_perc = f"{params.get('securityFactorPerc', 0):.1%}"
        loan_data.estimate_fee = f"{params.get('estimateFee', 0):,.2f} Euro"
        loan_data.estimate_fee_perc = f"{params.get('estimateFeePerc', 0):.2%}"
        loan_data.entry_fee_perc = f"{params.get('entryFeePerc', 0):.2%}"
        loan_data.risk_fee_perc = f"{params.get('riskFeePerc', 0):.2%}"
        
        # Set min/max values (static for Bank Austria)
        loan_data.min_betrag = "50000"
        loan_data.max_betrag = "3000000"
        loan_data.min_laufzeit = "120"  # 10 years
        loan_data.max_laufzeit = "408"  # 34 years
        
        # Store raw API data
        loan_data.raw_data = json.dumps(api_data, ensure_ascii=False)
    
    def _set_fallback_data(self, loan_data: LoanData, loan_amount: int, duration_months: int):
        """Set fallback data when API fails"""
        loan_data.nettokreditbetrag = f"{loan_amount:,} Euro"
        loan_data.sollzinssatz = "3.0% p.a."
        loan_data.effektiver_jahreszins = "3.342% p.a."
        loan_data.vertragslaufzeit = f"{duration_months} Monate"
        loan_data.min_betrag = "50000"
        loan_data.max_betrag = "3000000"
        loan_data.raw_data = "API call failed - using fallback data"


class BankScraperFactory:
    """Factory class to create bank scrapers"""
    
    @staticmethod
    def create_scraper(bank_name: str, driver_manager: WebDriverManager) -> BaseBankScraper:
        """Create a scraper instance for the specified bank"""
        scrapers = {
            'raiffeisen': RaiffeisenScraper,
            'bank99': Bank99Scraper,
            'erste': ErsteScraper,
            'bankaustria': BankAustriaScraper
        }
        
        if bank_name not in scrapers:
            raise ValueError(f"Unknown bank: {bank_name}")
        
        return scrapers[bank_name](driver_manager)


class ReportGenerator:
    """Generates reports in various formats"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
    
    def generate_html_report(self, filename: str = 'bank_comparison_housing_loan.html') -> str:
        """Generate HTML comparison report"""
        try:
            data = self.db_manager.get_latest_data()
            
            html_content = self._create_html_content(data)
            
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            logger.info(f"HTML report generated: {filename}")
            return html_content
            
        except Exception as e:
            logger.error(f"Error generating HTML report: {e}")
            return ""
    
    def _create_html_content(self, data: List[Dict]) -> str:
        """Create HTML content from data"""
        # Create bank headers
        bank_headers = ''.join(
            f'<th class="bank-name">{row["bank_name"].capitalize()}</th>' 
            for row in data
        )
        
        # Create parameter rows
        parameters = [
            ('Sollzinssatz', 'rate'),
            ('Effektiver Jahreszins', 'effektiver_jahreszins'),
            ('Nettokreditbetrag', 'nettokreditbetrag'),
            ('Vertragslaufzeit', 'vertragslaufzeit'),
            ('Gesamtbetrag', 'gesamtbetrag'),
            ('Monatliche Rate', 'monatliche_rate'),
            ('Min. Kreditbetrag', 'min_betrag'),
            ('Max. Kreditbetrag', 'max_betrag'),
            ('Min. Laufzeit (Monate)', 'min_laufzeit'),
            ('Max. Laufzeit (Monate)', 'max_laufzeit'),
            # Additional Bank Austria API fields
            ('Bearbeitungsspesen', 'bearbeitungsspesen'),
            ('Schatzgebuhr', 'schatzgebuhr'),
            ('Eintragungsgebuhr', 'eintragungsgebuhr'),
            ('Risikovorsorge', 'risikovorsorge'),
            ('Kontofuhrung Viertel', 'kontofuhrung_viertel'),
            ('Sicherheitsfaktor', 'sicherheitsfaktor'),
            ('Rate mit Kontofuhrung', 'rate_kontofuhrung'),
            ('Anzahl Zahlungen', 'payments_total'),
            ('Kontofuhrung monatlich', 'account_fee_monthly'),
            ('Bearbeitungsgebühr %', 'processing_fee_perc'),
            ('Sicherheitsfaktor %', 'security_factor_perc'),
            ('Schätzung Gebühr', 'estimate_fee'),
            ('Schätzung Gebühr %', 'estimate_fee_perc'),
            ('Eintragungsgebühr %', 'entry_fee_perc'),
            ('Risikogebühr %', 'risk_fee_perc'),
            # Erste Bank (Sparkasse) specific fields
            ('Rate Fix', 'installment_fixed'),
            ('Rate Intern', 'installment_internal'),
            ('Zinssatz Fix', 'fixed_interest_rate'),
            ('Zinssatz Variabel', 'variable_interest_rate'),
            ('Fix-Phase (Monate)', 'fixed_phase_months'),
            ('Variabel-Phase (Monate)', 'variable_phase_months'),
            ('Vermittlungsgebühr %', 'brokerage_fee_perc'),
            ('Kontoführung Quartal', 'account_management_quarterly'),
            ('Eigenmittelgebühr %', 'equity_procurement_fee_perc'),
            ('Eintragungsgebühr % (Erste)', 'entry_fee_perc_erste'),
            ('Beglaubigungskosten', 'authentication_costs'),
            ('Produkttyp', 'product_type'),
            ('Voraussetzungen', 'requirements'),
            ('Berechnungsdatum', 'calculation_date')
        ]
        
        parameter_rows = ''
        for param_name, param_key in parameters:
            cells = ''.join(
                f'<td class="value">{row.get(param_key, "")}</td>' 
                for row in data
            )
            parameter_rows += f'''
                <tr>
                    <td class="parameter-name">{param_name}</td>
                    {cells}
                </tr>
            '''
        
        return f'''
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Austrian Banks Interest Rate Comparison</title>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    margin: 20px;
                    background-color: #f5f5f5;
                }}
                .container {{
                    max-width: 1200px;
                    margin: 0 auto;
                    background-color: white;
                    padding: 20px;
                    border-radius: 8px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }}
                h1 {{
                    color: #333;
                    text-align: center;
                    margin-bottom: 30px;
                }}
                .table-responsive {{
                    width: 100%;
                    overflow-x: auto;
                }}
                table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin-bottom: 20px;
                    min-width: 600px;
                }}
                th, td {{
                    padding: 12px;
                    text-align: left;
                    border-bottom: 1px solid #ddd;
                    white-space: nowrap;
                }}
                th {{
                    background-color: #f8f9fa;
                    font-weight: bold;
                }}
                tr:hover {{
                    background-color: #f5f5f5;
                }}
                .timestamp {{
                    text-align: center;
                    color: #666;
                    font-size: 0.9em;
                    margin-top: 20px;
                }}
                .bank-name {{
                    font-weight: bold;
                    color: #2c3e50;
                }}
                .value {{
                    font-family: monospace;
                }}
                .parameter-name {{
                    font-weight: bold;
                    background-color: #f8f9fa;
                }}
                @media (max-width: 700px) {{
                    body {{
                        margin: 0;
                        padding: 0;
                    }}
                    .container {{
                        margin: 0;
                        padding: 5px;
                        border-radius: 0;
                        box-shadow: none;
                    }}
                    table {{
                        font-size: 12px;
                        min-width: 400px;
                    }}
                    th, td {{
                        padding: 6px;
                    }}
                    h1 {{
                        font-size: 1.2em;
                        margin-bottom: 10px;
                    }}
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Austrian Banks Interest Rate Comparison</h1>
                <div class="table-responsive">
                    <table>
                        <thead>
                            <tr>
                                <th>Parameter</th>
                                {bank_headers}
                            </tr>
                        </thead>
                        <tbody>
                            {parameter_rows}
                        </tbody>
                    </table>
                </div>
                <div class="timestamp">
                    Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                </div>
            </div>
        </body>
        </html>
        '''


class EmailService:
    """Handles email sending functionality"""
    
    def __init__(self):
        self.email_host = os.getenv('EMAIL_HOST')
        self.email_port = int(os.getenv('EMAIL_PORT', '587'))
        self.email_user = os.getenv('EMAIL_USER')
        self.email_password = os.getenv('EMAIL_PASSWORD')
        self.email_recipients = os.getenv('EMAIL_RECIPIENTS_WOHNKREDIT', '').split(',')
    
    def send_report(self, html_content: str, subject: str = "Aktuelle Konditionen Konsumredite in Österreich"):
        """Send email report with HTML content and attachments"""
        try:
            if not all([self.email_host, self.email_port, self.email_user, self.email_password, self.email_recipients]):
                logger.error("Missing email configuration in .env file")
                return False
            
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.email_user
            msg['To'] = ', '.join(self.email_recipients)
            
            # Attach HTML content
            html_part = MIMEText(html_content, 'html')
            msg.attach(html_part)
            
            # Add screenshot attachments (DISABLED)
            # self._add_screenshot_attachments(msg)
            
            # Send email
            with smtplib.SMTP(self.email_host, self.email_port) as server:
                server.starttls()
                server.login(self.email_user, self.email_password)
                server.send_message(msg)
            
            logger.info(f"Email sent successfully to {', '.join(self.email_recipients)}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending email: {e}")
            return False
    
    def _add_screenshot_attachments(self, msg: MIMEMultipart):
        """Add screenshot attachments to email"""
        screenshots_dir = './screenshots'
        if not os.path.exists(screenshots_dir):
            logger.warning("Screenshots directory not found")
            return
        
        screenshot_files = glob.glob(os.path.join(screenshots_dir, '*'))
        
        for file_path in screenshot_files:
            if os.path.isfile(file_path):
                try:
                    filename = os.path.basename(file_path)
                    
                    with open(file_path, 'rb') as attachment:
                        part = MIMEBase('application', 'octet-stream')
                        part.set_payload(attachment.read())
                    
                    encoders.encode_base64(part)
                    part.add_header(
                        'Content-Disposition',
                        f'attachment; filename= {filename}'
                    )
                    
                    msg.attach(part)
                    logger.info(f"Attached screenshot: {filename}")
                    
                except Exception as e:
                    logger.error(f"Error attaching {file_path}: {e}")


class ScraperOrchestrator:
    """Main orchestrator class that coordinates all scraping activities"""
    
    def __init__(self, enabled_banks: List[str] = None):
        self.enabled_banks = enabled_banks or ['bankaustria', 'erste', 'bank99']
        self.driver_manager = WebDriverManager()
        self.db_manager = DatabaseManager()
        self.report_generator = ReportGenerator(self.db_manager)
        self.email_service = EmailService()
        
        # Create screenshots directory if it doesn't exist
        os.makedirs('screenshots', exist_ok=True)
    
    def run(self):
        """Run the complete scraping process"""
        try:
            # Setup WebDriver
            self.driver_manager.setup_driver()
            
            # Scrape each enabled bank
            for bank_name in self.enabled_banks:
                try:
                    logger.info(f"Starting scraping for {bank_name}")
                    self._scrape_bank(bank_name)
                    time.sleep(2)  # Polite delay between banks
                except Exception as e:
                    logger.error(f"Error scraping {bank_name}: {e}")
                    continue
            
            # Generate reports
            self.db_manager.export_to_excel()
            html_content = self.report_generator.generate_html_report()
            
            # Send email report (DISABLED)
            # if html_content:
            #     self.email_service.send_report(html_content)
            
            logger.info("Scraping process completed successfully")
            
        except Exception as e:
            logger.error(f"Error during scraping process: {e}")
        finally:
            self.driver_manager.quit_driver()
    
    def _scrape_bank(self, bank_name: str):
        """Scrape a specific bank"""
        try:
            scraper = BankScraperFactory.create_scraper(bank_name, self.driver_manager)
            loan_data = scraper.scrape_loan_data()
            self.db_manager.store_loan_data(loan_data)
            logger.info(f"Successfully scraped {bank_name}")
        except Exception as e:
            logger.error(f"Error scraping {bank_name}: {e}")
            raise
    
    def add_bank_scraper(self, bank_name: str, scraper_class: type):
        """Add a new bank scraper (for extensibility)"""
        # This would be implemented to dynamically add new scrapers
        # For now, scrapers are registered in the factory
        pass


if __name__ == "__main__":
    # Create and run the orchestrator
    orchestrator = ScraperOrchestrator()
    orchestrator.run()
