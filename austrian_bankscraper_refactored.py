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
    
    def __init__(self, db_path: str = 'austrian_banks.db'):
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
                full_text TEXT
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
                monatliche_rate, min_betrag, max_betrag, min_laufzeit, max_laufzeit, full_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            loan_data.bank_name, loan_data.product_name, loan_data.sollzinssatz,
            loan_data.currency, loan_data.date_scraped, loan_data.source_url,
            loan_data.nettokreditbetrag, loan_data.gesamtbetrag, loan_data.vertragslaufzeit,
            loan_data.effektiver_jahreszins, loan_data.monatliche_rate, loan_data.min_betrag,
            loan_data.max_betrag, loan_data.min_laufzeit, loan_data.max_laufzeit, loan_data.raw_data
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
    
    def export_to_excel(self, filename: str = 'austrian_banks_data.xlsx'):
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


class BawagScraper(BaseBankScraper):
    """Scraper for BAWAG Bank"""
    
    def get_bank_name(self) -> str:
        return 'bawag'
    
    def get_base_url(self) -> str:
        return 'https://kreditrechner.bawag.at/'
    
    def scrape_loan_data(self, loan_amount: int = 10000, duration_months: int = 60) -> LoanData:
        """Scrape BAWAG loan data"""
        logger.info(f"Scraping {self.bank_name} loan data")
        
        self.driver.get(self.base_url)
        time.sleep(5)
        
        # Set loan amount
        self._set_loan_amount(loan_amount)
        
        # Set duration (convert months to years)
        duration_years = duration_months // 12
        self._set_duration(duration_years)
        
        time.sleep(5)  # Wait for calculation to update
        
        # Extract data from calculation table
        loan_data = self._extract_calculation_data()
        loan_data.source_url = self.base_url
        
        # Extract min/max values from sliders
        self._extract_slider_values(loan_data)
        
        self.take_screenshot()
        return loan_data
    
    def _set_loan_amount(self, amount: int):
        """Set the loan amount in the form"""
        try:
            kreditbetrag_input = self.wait.until(
                EC.element_to_be_clickable((By.ID, 'Kreditbetrag'))
            )
            self.driver.execute_script("arguments[0].scrollIntoView(true);", kreditbetrag_input)
            time.sleep(0.5)
            
            kreditbetrag_input.click()
            kreditbetrag_input.send_keys(Keys.CONTROL + "a")
            kreditbetrag_input.send_keys(Keys.DELETE)
            time.sleep(0.5)
            
            actions = ActionChains(self.driver)
            actions.send_keys(str(amount)).perform()
            kreditbetrag_input.send_keys(Keys.TAB)
            time.sleep(2)
            
            logger.info(f"Set loan amount to {amount}")
        except Exception as e:
            logger.warning(f"Could not set loan amount: {e}")
    
    def _set_duration(self, years: int):
        """Set the loan duration in years"""
        try:
            laufzeit_input = self.wait.until(
                EC.element_to_be_clickable((By.ID, 'time'))
            )
            self.driver.execute_script("arguments[0].scrollIntoView(true);", laufzeit_input)
            time.sleep(0.5)
            
            laufzeit_input.click()
            laufzeit_input.send_keys(Keys.CONTROL + "a")
            laufzeit_input.send_keys(Keys.DELETE)
            time.sleep(0.5)
            
            actions = ActionChains(self.driver)
            actions.send_keys(str(years)).perform()
            laufzeit_input.send_keys(Keys.TAB)
            time.sleep(2)
            
            logger.info(f"Set duration to {years} years")
        except Exception as e:
            logger.warning(f"Could not set duration: {e}")
    
    def _extract_calculation_data(self) -> LoanData:
        """Extract data from the calculation table"""
        loan_data = LoanData(
            bank_name=self.bank_name,
            product_name='Representative Example'
        )
        
        try:
            calc_table = self.driver.find_element(By.CSS_SELECTOR, 'div.calculation-example.info-box table')
            rows = calc_table.find_elements(By.TAG_NAME, 'tr')
            
            for row in rows:
                cells = row.find_elements(By.TAG_NAME, 'td')
                if len(cells) == 2:
                    label = cells[0].text.strip().lower()
                    value = cells[1].text.strip()
                    
                    if 'kreditbetrag' in label:
                        loan_data.nettokreditbetrag = value
                    elif 'laufzeit' in label:
                        loan_data.vertragslaufzeit = value
                    elif 'sollzinssatz' in label:
                        loan_data.sollzinssatz = value.replace('p.a.', '').strip()
                    elif 'effektiver zinssatz' in label:
                        loan_data.effektiver_jahreszins = value.replace('p.a.', '').strip()
                    elif 'gesamtrückzahlung' in label:
                        loan_data.gesamtbetrag = value
            
            # Extract monthly rate
            try:
                min_monthly_div = self.driver.find_element(By.CSS_SELECTOR, 'div.min-monthly.align-left-right')
                spans = min_monthly_div.find_elements(By.TAG_NAME, 'span')
                if len(spans) > 1:
                    loan_data.monatliche_rate = spans[1].text.strip()
            except Exception as e:
                logger.warning(f"Could not extract monthly rate: {e}")
                
        except Exception as e:
            logger.error(f"Error extracting calculation data: {e}")
        
        return loan_data
    
    def _extract_slider_values(self, loan_data: LoanData):
        """Extract min/max values from slider attributes"""
        try:
            amount_slider = self.driver.find_element(By.ID, 'amount-slider')
            loan_data.min_betrag = amount_slider.get_attribute('min')
            loan_data.max_betrag = amount_slider.get_attribute('max')
            
            time_slider = self.driver.find_element(By.ID, 'time')
            min_years = time_slider.get_attribute('min')
            max_years = time_slider.get_attribute('max')
            
            # Convert years to months
            if min_years:
                loan_data.min_laufzeit = str(int(min_years) * 12)
            if max_years:
                loan_data.max_laufzeit = str(int(max_years) * 12)
                
        except Exception as e:
            logger.warning(f"Could not extract slider values: {e}")


class Bank99Scraper(BaseBankScraper):
    """Scraper for Bank99"""
    
    def get_bank_name(self) -> str:
        return 'bank99'
    
    def get_base_url(self) -> str:
        return 'https://bank99.at/kredit/rundumkredit99'
    
    def scrape_loan_data(self, loan_amount: int = 10000, duration_months: int = 60) -> LoanData:
        """Scrape Bank99 loan data"""
        logger.info(f"Scraping {self.bank_name} loan data")
        
        self.driver.get(self.base_url)
        time.sleep(3)
        
        # Extract min/max values from the page
        loan_data = LoanData(
            bank_name=self.bank_name,
            product_name='Representative Example',
            source_url=self.base_url
        )
        
        self._extract_min_max_from_page(loan_data)
        
        # Make API call for actual calculation
        self._fetch_api_data(loan_data, loan_amount, duration_months)
        
        self.take_screenshot()
        return loan_data
    
    def _extract_min_max_from_page(self, loan_data: LoanData):
        """Extract min/max values from the webpage"""
        try:
            li_elements = self.driver.find_elements(By.CSS_SELECTOR, 'ul#acn-list > li')
            
            for li in li_elements:
                try:
                    left = li.find_element(By.CSS_SELECTOR, '.left')
                    right = li.find_element(By.CSS_SELECTOR, '.right')
                    
                    # Find label
                    label = None
                    headline_divs = left.find_elements(By.CSS_SELECTOR, 'div.headline')
                    for hd in headline_divs:
                        ps = hd.find_elements(By.TAG_NAME, 'p')
                        if ps:
                            label = ps[0].text.strip().lower()
                            break
                    
                    if not label:
                        ps = left.find_elements(By.TAG_NAME, 'p')
                        if ps:
                            label = ps[0].text.strip().lower()
                    
                    right_text = right.text.strip()
                    
                    if label and 'kreditsumme' in label:
                        match = re.search(r'€\s*([\d\.]+)\s*-\s*€?\s*([\d\.]+)', right_text)
                        if match:
                            loan_data.min_betrag = match.group(1).replace('.', '')
                            loan_data.max_betrag = match.group(2).replace('.', '')
                    elif label and 'laufzeit' in label:
                        match = re.search(r'(\d+)\s*-\s*(\d+)', right_text)
                        if match:
                            loan_data.min_laufzeit = match.group(1)
                            loan_data.max_laufzeit = match.group(2)
                            
                except Exception as e:
                    logger.warning(f"Error parsing li element: {e}")
                    
        except Exception as e:
            logger.warning(f"Could not extract min/max values: {e}")
    
    def _fetch_api_data(self, loan_data: LoanData, loan_amount: int, duration_months: int):
        """Fetch calculation data from API"""
        try:
            api_url = f"https://pwa.bank99.at/public-web-api/kreditrechner?produkt=ratenkredit&betrag={loan_amount}&laufzeit={duration_months}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            
            response = requests.get(api_url, headers=headers, timeout=10)
            response.raise_for_status()
            
            # Parse XML response
            root = ET.fromstring(response.text)
            
            loan_data.nettokreditbetrag = self._get_xml_value(root, 'betrag')
            loan_data.monatliche_rate = self._get_xml_value(root, 'rate')
            loan_data.gesamtbetrag = self._get_xml_value(root, 'gesamtbelastung')
            loan_data.sollzinssatz = self._get_xml_value(root, 'nominalzinssatz')
            loan_data.effektiver_jahreszins = self._get_xml_value(root, 'effektivzinssatz')
            loan_data.vertragslaufzeit = self._get_xml_value(root, 'laufzeit')
            loan_data.raw_data = response.text
            
            logger.info(f"Bank99 API data extracted successfully")
            
        except Exception as e:
            logger.error(f"Error fetching API data: {e}")
    
    def _get_xml_value(self, root, tag_name: str) -> Optional[str]:
        """Get value from XML element"""
        element = root.find(tag_name)
        return element.text if element is not None else None


class ErsteScraper(BaseBankScraper):
    """Scraper for Erste Bank"""
    
    def get_bank_name(self) -> str:
        return 'erste'
    
    def get_base_url(self) -> str:
        return 'https://shop.sparkasse.at/storeconsumerloan/rest/emilcalculators/198'
    
    def scrape_loan_data(self, loan_amount: int = 10000, duration_months: int = 60) -> LoanData:
        """Scrape Erste Bank loan data"""
        logger.info(f"Scraping {self.bank_name} loan data")
        
        loan_data = LoanData(
            bank_name=self.bank_name,
            product_name='Representative Example',
            source_url=self.base_url
        )
        
        # Fetch min/max values with GET request
        self._fetch_min_max_values(loan_data)
        
        # Fetch calculation data with PUT request
        self._fetch_calculation_data(loan_data, loan_amount, duration_months)
        
        return loan_data
    
    def _fetch_min_max_values(self, loan_data: LoanData):
        """Fetch min/max values from GET request"""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            
            response = requests.get(self.base_url, headers=headers, verify=False)
            response.raise_for_status()
            data = response.json()
            
            loan_data.min_betrag = str(data.get('minimumAmount', ''))
            loan_data.max_betrag = str(data.get('maximumAmount', ''))
            loan_data.min_laufzeit = str(data.get('minimumDuration', ''))
            loan_data.max_laufzeit = str(data.get('maximumDuration', ''))
            
        except Exception as e:
            logger.warning(f"Could not fetch min/max values: {e}")
    
    def _fetch_calculation_data(self, loan_data: LoanData, loan_amount: int, duration_months: int):
        """Fetch calculation data from PUT request"""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Content-Type": "application/vnd.at.spardat.store.consumerloan.representation.consumer.loan.calulation.input+json",
                "Accept": "application/vnd.at.spardat.store.consumerloan.representation.consumer.loan.calulation.output+json",
                "Origin": "https://www.sparkasse.at",
                "Referer": "https://www.sparkasse.at/"
            }
            
            payload = {
                "loanAmount": loan_amount,
                "loanDuration": duration_months,
                "includeInsurance": False
            }
            
            response = requests.put(self.base_url, headers=headers, json=payload, verify=False)
            response.raise_for_status()
            data = response.json()
            
            loan_data.sollzinssatz = data.get('interestRate')
            loan_data.effektiver_jahreszins = data.get('effectiveInterestRate')
            loan_data.monatliche_rate = data.get('installment')
            loan_data.gesamtbetrag = data.get('totalAmount')
            loan_data.raw_data = str(data)
            
            # Extract from calculationDetails
            if 'calculationDetails' in data and 'list' in data['calculationDetails']:
                for item in data['calculationDetails']['list']:
                    if item.get('name') == 'Auszahlungsbetrag:':
                        loan_data.nettokreditbetrag = item.get('value')
                    elif item.get('name') == 'Laufzeit:':
                        loan_data.vertragslaufzeit = item.get('value')
            
            logger.info(f"Erste Bank calculation data extracted successfully")
            
        except Exception as e:
            logger.error(f"Error fetching calculation data: {e}")


class BankScraperFactory:
    """Factory class to create bank scrapers"""
    
    @staticmethod
    def create_scraper(bank_name: str, driver_manager: WebDriverManager) -> BaseBankScraper:
        """Create a scraper instance for the specified bank"""
        scrapers = {
            'raiffeisen': RaiffeisenScraper,
            'bawag': BawagScraper,
            'bank99': Bank99Scraper,
            'erste': ErsteScraper
        }
        
        if bank_name not in scrapers:
            raise ValueError(f"Unknown bank: {bank_name}")
        
        return scrapers[bank_name](driver_manager)


class ReportGenerator:
    """Generates reports in various formats"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
    
    def generate_html_report(self, filename: str = 'bank_comparison.html') -> str:
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
            ('Max. Laufzeit (Monate)', 'max_laufzeit')
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
        self.email_recipients = os.getenv('EMAIL_RECIPIENTS', '').split(',')
    
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
            
            # Add screenshot attachments
            self._add_screenshot_attachments(msg)
            
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
        self.enabled_banks = enabled_banks or ['raiffeisen', 'bawag', 'bank99', 'erste']
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
            
            # Send email report
            if html_content:
                self.email_service.send_report(html_content)
            
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