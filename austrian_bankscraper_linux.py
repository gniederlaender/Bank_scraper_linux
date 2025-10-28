#!/usr/bin/env python3
import requests
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
import pandas as pd
import sqlite3
import json
import logging
from datetime import datetime
import time
from fake_useragent import UserAgent
import os
from dotenv import load_dotenv
import re
import signal
import subprocess
import sys
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import glob
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scraper.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class TimeoutError(Exception):
    pass

def timeout_handler(signum, frame):
    raise TimeoutError("Operation timed out")

class AustrianBankScraper:
    def __init__(self):
        self.banks = {
            'raiffeisen': {
                'url': 'https://www.raiffeisen.at/noew/rlb/de/privatkunden/kredit-leasing/der-faire-credit.html',
                'interest_rates_url': 'https://www.raiffeisen.at/noew/rlb/de/privatkunden/kredit-leasing/der-faire-credit.html'
            },
            'bawag': {
                'url': 'https://kreditrechner.bawag.at/',
                'interest_rates_url': 'https://kreditrechner.bawag.at/'
            },
            'bank99': {
                'url': 'https://bank99.at/kredit/rundumkredit99',
                'interest_rates_url': 'https://bank99.at/kredit/rundumkredit99'
            },
            'erste': {
                'url': 'https://www.erstebank.at/at/de/privatkunden/kredite/rundumkredit.html',
                'interest_rates_url': 'https://shop.sparkasse.at/storeconsumerloan/rest/emilcalculators/198'
            },
            'santander': {
                'url': 'https://www.santanderconsumer.at/',
                'interest_rates_url': 'https://website-public-api.santanderconsumer.at/api/public'
            }
        }
        
        # Mapping table for field names by bank
        self.field_mapping = {
            'raiffeisen': {
                'sollzinssatz': 'Sollzinssatz',
                'effektiver_jahreszins': 'effektiver Jahreszins',
                'nettokreditbetrag': 'Nettokreditbetrag',
                'vertragslaufzeit': 'Vertragslaufzeit',
                'gesamtbetrag': 'Gesamtbetrag',
                'monatliche_rate': 'monatliche Rate'
            },
            'bawag': {
                'sollzinssatz': 'Nominalzinssatz in Höhe von',
                'effektiver_jahreszins': 'Effektivzinssatz',
                'nettokreditbetrag': 'Nettodarlehensbetrag von',
                'vertragslaufzeit': 'Laufzeit von',
                'gesamtbetrag': 'Gesamtrückzahlung',
                'monatliche_rate': 'Monatliche Rate'
            },
            'bank99': {
                'sollzinssatz': 'nominalzinssatz',  # API field name
                'effektiver_jahreszins': 'effektivzinssatz',  # API field name
                'nettokreditbetrag': 'betrag',  # API field name
                'vertragslaufzeit': 'laufzeit',  # API field name
                'gesamtbetrag': 'gesamtbelastung',  # API field name
                'monatliche_rate': 'rate'  # API field name
            },
            'erste': {
                'sollzinssatz': 'interestRate',
                'effektiver_jahreszins': 'effectiveInterestRate',
                'nettokreditbetrag': 'startAmount',
                'vertragslaufzeit': 'startDuration',
                'gesamtbetrag': None,
                'monatliche_rate': 'installment'
            },
            'santander': {
                'sollzinssatz': 'nominal_rate',  # API field name
                'effektiver_jahreszins': 'effective_rate',  # API field name
                'nettokreditbetrag': 'amount',  # API field name
                'vertragslaufzeit': 'duration',  # API field name
                'gesamtbetrag': 'total_amount',  # API field name
                'monatliche_rate': 'rate'  # API field name
            }
        }
        
        # Switch to enable/disable scraping for each bank
        self.enable_scraping = {
            'raiffeisen': True,
            'bawag': True,
            'bank99': True,
            'erste': True,
            'santander': True
        }
        
        self.ua = UserAgent()
        self.setup_selenium()
        self.init_database()

    def setup_selenium(self):
        """Set up Firefox WebDriver with appropriate options"""
        # Set environment variables
        os.environ['MOZ_HEADLESS'] = '1'
        os.environ['MOZ_DISABLE_CONTENT_SANDBOX'] = '1'
        
        # Create options
        options = Options()
        options.add_argument('--headless')
        options.set_preference('general.useragent.override', self.ua.random)
        
        # Create service with explicit log
        service = Service(
            executable_path='/usr/local/bin/geckodriver',
            log_output='geckodriver.log'
        )
        
        logger.info("Creating Firefox driver...")
        
        # Set timeout
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(30)  # 30 second timeout
        
        try:
            self.driver = webdriver.Firefox(service=service, options=options)
            signal.alarm(0)  # Cancel timeout
            logger.info("Firefox driver created successfully!")
            self.wait = WebDriverWait(self.driver, 10)
        except TimeoutError:
            logger.error("Timeout: Firefox took too long to start")
            raise
        except Exception as e:
            signal.alarm(0)  # Cancel timeout
            logger.error(f"Error creating Firefox driver: {e}")
            raise

    def init_database(self):
        """Initialize SQLite database and create necessary tables"""
        conn = sqlite3.connect('austrian_banks.db')
        cursor = conn.cursor()
        
        # Create tables for different types of data
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

    def get_page_content(self, url):
        """Get page content with retry mechanism"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                headers = {'User-Agent': self.ua.random}
                response = requests.get(url, headers=headers, timeout=10)
                response.raise_for_status()
                return response.text
            except Exception as e:
                logger.error(f"Attempt {attempt + 1} failed for {url}: {str(e)}")
                if attempt == max_retries - 1:
                    raise
                time.sleep(2 ** attempt)  # Exponential backoff

    def scrape_interest_rates(self, bank_name):
        """Scrape interest rates for a specific bank"""
        try:
            url = self.banks[bank_name]['interest_rates_url']
            logger.info(f"Scraping interest rates for {bank_name}")
            
            self.driver.get(url)
            time.sleep(5)  # Add a delay to let the page load completely
            
            if bank_name == 'raiffeisen':
                # Extract interest rate and fees from the specified element
                try:
                    # Wait longer for the element to be present
                    time.sleep(10)  # Increased wait time
                    
                    # Try different selectors
                    selectors = [
                        '.credit-calculator-dfc-representative-calc',
                        '[class*="representative-calc"]',  # More flexible selector
                        '[class*="credit-calculator"]'     # Even more flexible
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
                    
                    # Parse the text to extract specific fields using the mapping
                    mapping = self.field_mapping[bank_name]
                    sollzinssatz = re.search(rf"{mapping['sollzinssatz']}: ([\d,]+ %)", text).group(1) if re.search(rf"{mapping['sollzinssatz']}: ([\d,]+ %)", text) else None
                    effektiver_jahreszins = re.search(rf"{mapping['effektiver_jahreszins']}: ([\d,]+ %)", text).group(1) if re.search(rf"{mapping['effektiver_jahreszins']}: ([\d,]+ %)", text) else None
                    nettokreditbetrag = re.search(rf"{mapping['nettokreditbetrag']}: ([\d,.]+ Euro)", text).group(1) if re.search(rf"{mapping['nettokreditbetrag']}: ([\d,.]+ Euro)", text) else None
                    vertragslaufzeit = re.search(rf"{mapping['vertragslaufzeit']}: ([\d]+ Monate)", text).group(1) if re.search(rf"{mapping['vertragslaufzeit']}: ([\d]+ Monate)", text) else None
                    gesamtbetrag = re.search(rf"{mapping['gesamtbetrag']}: ([\d,.]+ Euro)", text).group(1) if re.search(rf"{mapping['gesamtbetrag']}: ([\d,.]+ Euro)", text) else None
                    monatliche_rate = re.search(rf"{mapping['monatliche_rate']}: ([\d,.]+ Euro)", text).group(1) if re.search(rf"{mapping['monatliche_rate']}: ([\d,.]+ Euro)", text) else None

                    # Parse min/max amount and duration from the Produktangaben part (in months)
                    min_betrag = max_betrag = min_laufzeit = max_laufzeit = None
                    try:
                        # Find Produktangaben part
                        produktangaben_match = re.search(r'Produktangaben:(.*)', text)
                        if produktangaben_match:
                            produktangaben = produktangaben_match.group(1)
                            # min_betrag and max_betrag from Nettokreditbetrag: 1.000 - 75.000 Euro
                            betrag_match = re.search(r'Nettokreditbetrag: ([\d\.]+)\s*-\s*([\d\.]+) Euro', produktangaben)
                            if betrag_match:
                                min_betrag = betrag_match.group(1).replace('.', '')
                                max_betrag = betrag_match.group(2).replace('.', '')
                            # min_laufzeit and max_laufzeit from Vertragslaufzeit: 12 - 84 Monate
                            laufzeit_match = re.search(r'Vertragslaufzeit: (\d+)\s*-\s*(\d+) Monate', produktangaben)
                            if laufzeit_match:
                                min_laufzeit = laufzeit_match.group(1)
                                max_laufzeit = laufzeit_match.group(2)
                    except Exception as e:
                        logger.warning(f"Could not parse min/max amount or duration for Raiffeisen: {e}")

                    self.store_interest_rate(
                        bank_name, 'Representative Example', sollzinssatz, 'EUR', url, nettokreditbetrag, gesamtbetrag, vertragslaufzeit, effektiver_jahreszins, monatliche_rate, text,
                        min_betrag, max_betrag, min_laufzeit, max_laufzeit
                    )

                    # Take a screenshot for debugging to verify the input value
                    screenshot_name = f"raiffeisen_debug_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                    self.driver.save_screenshot(screenshot_name)
                    logger.info(f"Debug screenshot saved as: {screenshot_name}")

                except Exception as e:
                    logger.error(f"Error processing Raiffeisen data: {str(e)}")
                    # Take a screenshot for debugging
                    self.driver.save_screenshot('raiffeisen_error.png')
                    raise
            
            elif bank_name == 'bawag':
                # Set Kreditbetrag to 10000 before scraping
                try:
                    # Wait for element to be clickable
                    kreditbetrag_input = self.wait.until(
                        EC.element_to_be_clickable((By.ID, 'Kreditbetrag'))
                    )
                    # Scroll to element if needed
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", kreditbetrag_input)
                    time.sleep(0.5)
                    # Clear field thoroughly
                    kreditbetrag_input.click()
                    kreditbetrag_input.send_keys(Keys.CONTROL + "a")
                    kreditbetrag_input.send_keys(Keys.DELETE)
                    time.sleep(0.5)
                    # Enter value with ActionChains
                    actions = ActionChains(self.driver)
                    actions.send_keys('10000').perform()
                    # Trigger events
                    kreditbetrag_input.send_keys(Keys.TAB)
                    time.sleep(2)
                    # Verify the value was set
                    current_value = kreditbetrag_input.get_attribute('value')
                    logger.info(f"Current Kreditbetrag input value: {current_value}")
                    if current_value != '10000':
                        logger.warning(f"Expected '10000' but got '{current_value}'")
                        # Try JavaScript method as fallback
                        self.driver.execute_script("arguments[0].value = '10000';", kreditbetrag_input)
                        self.driver.execute_script("arguments[0].dispatchEvent(new Event('change'));", kreditbetrag_input)
                        time.sleep(1)
                        current_value = kreditbetrag_input.get_attribute('value')
                        logger.info(f"After JavaScript method: {current_value}")
                    logger.info("Successfully set Kreditbetrag to 10000 for BAWAG")
                except Exception as e:
                    logger.warning(f"Could not set Kreditbetrag to 10000 for BAWAG: {e}")
                
                # Set Laufzeit to 5 years (60 months)
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
                    actions.send_keys('5').perform()
                    laufzeit_input.send_keys(Keys.TAB)
                    time.sleep(2)
                    current_value = laufzeit_input.get_attribute('value')
                    logger.info(f"Current Laufzeit input value: {current_value}")
                    if current_value != '5':
                        logger.warning(f"Expected '5' but got '{current_value}'")
                        self.driver.execute_script("arguments[0].value = '5';", laufzeit_input)
                        self.driver.execute_script("arguments[0].dispatchEvent(new Event('change'));", laufzeit_input)
                        time.sleep(1)
                        current_value = laufzeit_input.get_attribute('value')
                        logger.info(f"After JavaScript method: {current_value}")
                    logger.info("Successfully set Laufzeit to 5 years for BAWAG")
                except Exception as e:
                    logger.warning(f"Could not set Laufzeit to 5 years for BAWAG: {e}")
                # Wait 5 seconds for the page to update with the new values
                time.sleep(5)
                
                # Extract from calculation-example table and min-monthly div
                sollzinssatz = effektiver_jahreszins = nettokreditbetrag = vertragslaufzeit = gesamtbetrag = monatliche_rate = None
                try:
                    # Find the calculation-example table
                    calc_table = self.driver.find_element(By.CSS_SELECTOR, 'div.calculation-example.info-box table')
                    rows = calc_table.find_elements(By.TAG_NAME, 'tr')
                    for row in rows:
                        cells = row.find_elements(By.TAG_NAME, 'td')
                        if len(cells) == 2:
                            label = cells[0].text.strip().lower()
                            value = cells[1].text.strip()
                            if 'kreditbetrag' in label:
                                nettokreditbetrag = value
                            elif 'laufzeit' in label:
                                vertragslaufzeit = value
                            elif 'sollzinssatz' in label:
                                sollzinssatz = value.replace('p.a.', '').strip()
                            elif 'effektiver zinssatz' in label:
                                effektiver_jahreszins = value.replace('p.a.', '').strip()
                            elif 'gesamtrückzahlungsbetrag' in label or 'gesamtrückzahlung' in label:
                                gesamtbetrag = value
                    # Find monatliche_rate from min-monthly div
                    try:
                        min_monthly_div = self.driver.find_element(By.CSS_SELECTOR, 'div.min-monthly.align-left-right')
                        spans = min_monthly_div.find_elements(By.TAG_NAME, 'span')
                        if len(spans) > 1:
                            monatliche_rate = spans[1].text.strip()
                    except Exception as e:
                        logger.warning(f"Could not parse monatliche_rate for BAWAG: {e}")
                except Exception as e:
                    logger.error(f"Error parsing BAWAG calculation-example: {e}")
                # Parse min/max amount and duration from the slider attributes (in months)
                min_betrag = max_betrag = min_laufzeit = max_laufzeit = None
                try:
                    amount_slider = self.driver.find_element(By.ID, 'amount-slider')
                    min_betrag = amount_slider.get_attribute('min')
                    max_betrag = amount_slider.get_attribute('max')
                    time_slider = self.driver.find_element(By.ID, 'time')
                    min_laufzeit_years = time_slider.get_attribute('min')
                    max_laufzeit_years = time_slider.get_attribute('max')
                    # Convert years to months
                    min_laufzeit = str(int(min_laufzeit_years) * 12) if min_laufzeit_years else None
                    max_laufzeit = str(int(max_laufzeit_years) * 12) if max_laufzeit_years else None
                except Exception as e:
                    logger.warning(f"Could not parse min/max amount or duration for BAWAG: {e}")
                self.store_interest_rate(
                    bank_name, 'Representative Example', sollzinssatz, 'EUR', url, nettokreditbetrag, gesamtbetrag, vertragslaufzeit, effektiver_jahreszins, monatliche_rate, None,
                    min_betrag, max_betrag, min_laufzeit, max_laufzeit
                )
            
            elif bank_name == 'bank99':
                # Wait for the page to load
                time.sleep(3)

                # Scrape min/max amount and duration from the page
                min_betrag = max_betrag = min_laufzeit = max_laufzeit = None
                try:
                    li_elements = self.driver.find_elements(By.CSS_SELECTOR, 'ul#acn-list > li')
                    for i, li in enumerate(li_elements):
                        try:
                            left = li.find_element(By.CSS_SELECTOR, '.left')
                            right = li.find_element(By.CSS_SELECTOR, '.right')
                            
                            # Find the label in the headline div's <p>
                            headline_divs = left.find_elements(By.CSS_SELECTOR, 'div.headline')
                            label = None
                            for hd in headline_divs:
                                ps = hd.find_elements(By.TAG_NAME, 'p')
                                if ps:
                                    label = ps[0].text.strip().lower()
                                    break
                            if not label:
                                # fallback: try to find any <p> in left
                                ps = left.find_elements(By.TAG_NAME, 'p')
                                if ps:
                                    label = ps[0].text.strip().lower()
                            
                            right_text = right.text.strip()
                            
                            if label:
                                if 'kreditsumme' in label:
                                    match = re.search(r'€\s*([\d\.]+)\s*-\s*€?\s*([\d\.]+)', right_text)
                                    if match:
                                        min_betrag = match.group(1).replace('.', '')
                                        max_betrag = match.group(2).replace('.', '')
                                        logger.info(f"Bank99 min_betrag: {min_betrag}, max_betrag: {max_betrag}")
                                elif 'laufzeit' in label:
                                    match = re.search(r'(\d+)\s*-\s*(\d+)', right_text)
                                    if match:
                                        min_laufzeit = match.group(1)
                                        max_laufzeit = match.group(2)
                                        logger.info(f"Bank99 min_laufzeit: {min_laufzeit}, max_laufzeit: {max_laufzeit}")
                        except Exception as e:
                            logger.warning(f"Error parsing li element {i} for Bank99 min/max: {e}")
                except Exception as e:
                    logger.warning(f"Could not parse min/max amount or duration for Bank99: {e}")
                
                # Make API call to get the calculation data
                try:
                    api_url = "https://pwa.bank99.at/public-web-api/kreditrechner?produkt=ratenkredit&betrag=10000&laufzeit=60"
                    headers = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                    }
                    response = requests.get(api_url, headers=headers, timeout=10)
                    response.raise_for_status()
                    
                    # Parse XML response
                    import xml.etree.ElementTree as ET
                    root = ET.fromstring(response.text)
                    
                    # Extract the required fields directly from the root (which is berechnung)
                    nettokreditbetrag = root.find('betrag').text if root.find('betrag') is not None else None
                    monatliche_rate = root.find('rate').text if root.find('rate') is not None else None
                    gesamtbetrag = root.find('gesamtbelastung').text if root.find('gesamtbelastung') is not None else None
                    sollzinssatz = root.find('nominalzinssatz').text if root.find('nominalzinssatz') is not None else None
                    effektiver_jahreszins = root.find('effektivzinssatz').text if root.find('effektivzinssatz') is not None else None
                    vertragslaufzeit = root.find('laufzeit').text if root.find('laufzeit') is not None else None
                    
                    logger.info(f"Bank99 API response extracted - betrag: {nettokreditbetrag}, rate: {monatliche_rate}, gesamtbelastung: {gesamtbetrag}, nominalzinssatz: {sollzinssatz}, effektivzinssatz: {effektiver_jahreszins}, laufzeit: {vertragslaufzeit}")
                        
                except Exception as e:
                    logger.error(f"Error making API call for Bank99: {str(e)}")
                    nettokreditbetrag = monatliche_rate = gesamtbetrag = sollzinssatz = effektiver_jahreszins = vertragslaufzeit = None
                
                self.store_interest_rate(
                    bank_name, 'Representative Example', sollzinssatz, 'EUR', url, nettokreditbetrag, gesamtbetrag, vertragslaufzeit, effektiver_jahreszins, monatliche_rate, f"API Response: {response.text if 'response' in locals() else 'No response'}",
                    min_betrag, max_betrag, min_laufzeit, max_laufzeit
                )

            
            elif bank_name == 'erste':

                api_url = self.banks[bank_name]['interest_rates_url']
                # Fetch min/max values with GET request
                min_betrag = max_betrag = min_laufzeit = max_laufzeit = None
                try:
                    get_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
                    get_response = requests.get(api_url, headers=get_headers, verify=False)
                    get_response.raise_for_status()
                    get_data = get_response.json()
                    min_betrag = str(get_data.get('minimumAmount')) if get_data.get('minimumAmount') is not None else None
                    max_betrag = str(get_data.get('maximumAmount')) if get_data.get('maximumAmount') is not None else None
                    min_laufzeit = str(get_data.get('minimumDuration')) if get_data.get('minimumDuration') is not None else None
                    max_laufzeit = str(get_data.get('maximumDuration')) if get_data.get('maximumDuration') is not None else None
                except Exception as e:
                    logger.warning(f"Could not extract min/max values from GET: {e}")
                # Fetch JSON data directly from the API (PUT)
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                    "Content-Type": "application/vnd.at.spardat.store.consumerloan.representation.consumer.loan.calulation.input+json",
                    "Accept": "application/vnd.at.spardat.store.consumerloan.representation.consumer.loan.calulation.output+json",
                    "Origin": "https://www.sparkasse.at",
                    "Referer": "https://www.sparkasse.at/"
                }
                payload = {
                    "loanAmount": 10000,
                    "loanDuration": 60,
                    "includeInsurance": False
                }
                response = requests.put(api_url, headers=headers, json=payload, verify=False)
                response.raise_for_status()
                data = response.json()
                mapping = self.field_mapping[bank_name]
                sollzinssatz = data.get(mapping['sollzinssatz'])
                effektiver_jahreszins = data.get(mapping['effektiver_jahreszins'])
                # Extract nettokreditbetrag and vertragslaufzeit from calculationDetails['list']
                nettokreditbetrag = None
                vertragslaufzeit = None
                try:
                    for item in data['calculationDetails']['list']:
                        if item.get('name') == 'Auszahlungsbetrag:':
                            nettokreditbetrag = item.get('value')
                        if item.get('name') == 'Laufzeit:':
                            vertragslaufzeit = item.get('value')
                except Exception as e:
                    logger.warning(f"Could not extract values from calculationDetails list: {e}")
                monatliche_rate = data.get(mapping['monatliche_rate'])
                gesamtbetrag = data.get('totalAmount')

                # Store the extracted fields in the database
                self.store_interest_rate(
                    bank_name,
                    'Representative Example',
                    sollzinssatz,
                    'EUR',
                    api_url,
                    nettokreditbetrag,
                    gesamtbetrag,
                    vertragslaufzeit,
                    effektiver_jahreszins,
                    monatliche_rate,
                    str(data),
                    min_betrag, max_betrag, min_laufzeit, max_laufzeit
                )
            
            elif bank_name == 'santander':
                # Santander uses GraphQL API
                api_url = self.banks[bank_name]['interest_rates_url']
                
                # Representative example: 10000 EUR, 60 months, 9.99% interest rate
                # Note: The API requires an interest rate to be provided
                payload = {
                    "operationName": "calculateCashLoan",
                    "variables": {
                        "amount": 10000,
                        "duration": 60,
                        "interestRate": 9.99
                    },
                    "query": """query calculateCashLoan($amount: Int!, $duration: Int!, $interestRate: Float!) {
  calculateCashLoan(
    amount: $amount
    duration: $duration
    interestRate: $interestRate
  ) {
    amount
    duration
    effective_rate
    nominal_rate
    rate
    total_amount
    __typename
  }
}"""
                }
                
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                    "Content-Type": "application/json",
                    "Accept": "application/json"
                }
                
                sollzinssatz = effektiver_jahreszins = nettokreditbetrag = vertragslaufzeit = gesamtbetrag = monatliche_rate = None
                min_betrag = max_betrag = min_laufzeit = max_laufzeit = None
                
                try:
                    response = requests.post(api_url, json=payload, headers=headers, timeout=10)
                    response.raise_for_status()
                    data = response.json()
                    
                    if 'data' in data and 'calculateCashLoan' in data['data']:
                        result = data['data']['calculateCashLoan']
                        mapping = self.field_mapping[bank_name]
                        
                        # Extract values from API response
                        sollzinssatz_raw = result.get(mapping['sollzinssatz'])
                        effektiver_jahreszins_raw = result.get(mapping['effektiver_jahreszins'])
                        nettokreditbetrag_raw = result.get(mapping['nettokreditbetrag'])
                        vertragslaufzeit_raw = result.get(mapping['vertragslaufzeit'])
                        gesamtbetrag_raw = result.get(mapping['gesamtbetrag'])
                        monatliche_rate_raw = result.get(mapping['monatliche_rate'])
                        
                        # Format values to match other banks
                        sollzinssatz = f"{sollzinssatz_raw:.2f} %" if sollzinssatz_raw is not None else None
                        effektiver_jahreszins = f"{effektiver_jahreszins_raw:.2f} %" if effektiver_jahreszins_raw is not None else None
                        nettokreditbetrag = f"{int(nettokreditbetrag_raw):,} EUR" if nettokreditbetrag_raw is not None else None
                        vertragslaufzeit = f"{int(vertragslaufzeit_raw)} Monate" if vertragslaufzeit_raw is not None else None
                        gesamtbetrag = f"{float(gesamtbetrag_raw):,.2f} EUR" if gesamtbetrag_raw is not None else None
                        monatliche_rate = f"{float(monatliche_rate_raw):,.2f} EUR" if monatliche_rate_raw is not None else None
                        
                        logger.info(f"Santander API response extracted - nominal_rate: {sollzinssatz}, effective_rate: {effektiver_jahreszins}, amount: {nettokreditbetrag}, duration: {vertragslaufzeit}, total_amount: {gesamtbetrag}, rate: {monatliche_rate}")
                    else:
                        logger.error(f"Santander API returned unexpected structure: {data}")
                        if 'errors' in data:
                            logger.error(f"Santander API errors: {data['errors']}")
                
                except Exception as e:
                    logger.error(f"Error making API call for Santander: {str(e)}")
                    import traceback
                    traceback.print_exc()
                
                # Store the extracted fields in the database
                # Note: min/max values not available from API, set to None for now
                self.store_interest_rate(
                    bank_name,
                    'Representative Example',
                    sollzinssatz,
                    'EUR',
                    api_url,
                    nettokreditbetrag,
                    gesamtbetrag,
                    vertragslaufzeit,
                    effektiver_jahreszins,
                    monatliche_rate,
                    f"API Response: {response.text if 'response' in locals() else 'No response'}",
                    min_betrag, max_betrag, min_laufzeit, max_laufzeit
                )
            
        except Exception as e:
            logger.error(f"Error scraping interest rates for {bank_name}: {str(e)}")
            # Take a screenshot for debugging
            try:
                self.driver.save_screenshot(f"{bank_name}_error_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
            except:
                pass

    def store_interest_rate(self, bank_name, product_name, rate, currency, source_url, nettokreditbetrag=None, gesamtbetrag=None, vertragslaufzeit=None, effektiver_jahreszins=None, monatliche_rate=None, full_text=None, min_betrag=None, max_betrag=None, min_laufzeit=None, max_laufzeit=None):
        """Store interest rate in database"""
        conn = sqlite3.connect('austrian_banks.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO interest_rates (bank_name, product_name, rate, currency, date_scraped, source_url, nettokreditbetrag, gesamtbetrag, vertragslaufzeit, effektiver_jahreszins, monatliche_rate, min_betrag, max_betrag, min_laufzeit, max_laufzeit, full_text)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (bank_name, product_name, rate, currency, datetime.now(), source_url, nettokreditbetrag, gesamtbetrag, vertragslaufzeit, effektiver_jahreszins, monatliche_rate, min_betrag, max_betrag, min_laufzeit, max_laufzeit, full_text))
        conn.commit()
        conn.close()

    def export_to_excel(self):
        """Export all data to Excel file"""
        try:
            conn = sqlite3.connect('austrian_banks.db')
            
            # Read data from each table
            interest_rates_df = pd.read_sql_query("SELECT * FROM interest_rates", conn)
            
            # Create Excel writer
            with pd.ExcelWriter('austrian_banks_data.xlsx') as writer:
                interest_rates_df.to_excel(writer, sheet_name='Interest Rates', index=False)
            
            logger.info("Data exported to Excel successfully")
            
        except Exception as e:
            logger.error(f"Error exporting to Excel: {str(e)}")
        finally:
            conn.close()

    def generate_interest_rate_chart(self):
        """Generate interest rate chart using the database view"""
        try:
            conn = sqlite3.connect('austrian_banks.db')
            
            # Check if view exists
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='view' AND name='interest_rates_chart_ready'")
            view_exists = cursor.fetchone()
            
            if not view_exists:
                logger.warning("Chart-ready view does not exist, skipping chart generation")
                return False
            
            # Extract data from the view
            query = """
            SELECT 
                bank_name,
                effektiver_jahreszins_numeric as effektiver_jahreszins,
                date_scraped
            FROM interest_rates_chart_ready 
            WHERE effektiver_jahreszins_numeric IS NOT NULL 
            ORDER BY date_scraped, bank_name
            """
            
            df = pd.read_sql_query(query, conn)
            df['date_scraped'] = pd.to_datetime(df['date_scraped'])
            
            if df.empty:
                logger.warning("No data available for chart generation")
                return False
            
            # Group by bank and date
            chart_data = {}
            banks = df['bank_name'].unique()
            
            for bank in banks:
                bank_data = df[df['bank_name'] == bank].copy()
                bank_data = bank_data.sort_values('date_scraped')
                
                # Group by date and take the average rate for that day
                daily_rates = bank_data.groupby(bank_data['date_scraped'].dt.date)['effektiver_jahreszins'].mean()
                
                chart_data[bank] = {
                    'dates': daily_rates.index.tolist(),
                    'rates': daily_rates.values.tolist()
                }
            
            # Create the chart
            plt.figure(figsize=(12, 6))
            
            # Define colors for banks
            colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f']
            
            for i, (bank, data) in enumerate(chart_data.items()):
                if not data['dates'] or not data['rates']:
                    continue
                    
                # Convert dates to datetime objects
                dates = [datetime.combine(d, datetime.min.time()) for d in data['dates']]
                
                plt.plot(dates, data['rates'], 
                        marker='o', 
                        linewidth=2.5, 
                        markersize=6,
                        label=bank, 
                        color=colors[i % len(colors)])
            
            # Customize the plot
            plt.title('Effective Interest Rate Development - Austrian Banks', 
                      fontsize=14, fontweight='bold', pad=15)
            plt.xlabel('Date', fontsize=11, fontweight='bold')
            plt.ylabel('Effective Interest Rate (%)', fontsize=11, fontweight='bold')
            
            # Format x-axis
            plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%d.%m.%Y'))
            plt.xticks(rotation=45)
            
            # Add grid
            plt.grid(True, alpha=0.3, linestyle='--')
            
            # Add legend
            plt.legend(loc='best', frameon=True, shadow=True)
            
            # Adjust layout
            plt.tight_layout()
            
            # Save chart
            chart_filename = 'interest_rate_chart.png'
            plt.savefig(chart_filename, dpi=300, bbox_inches='tight', 
                       facecolor='white', edgecolor='none')
            plt.close()  # Close the figure to free memory
            
            logger.info(f"Interest rate chart generated successfully: {chart_filename}")
            return True
            
        except Exception as e:
            logger.error(f"Error generating interest rate chart: {str(e)}")
            return False
        finally:
            if 'conn' in locals():
                conn.close()

    def _get_chart_base64(self):
        """Convert chart image to base64 for HTML embedding"""
        try:
            import base64
            with open('interest_rate_chart.png', 'rb') as img_file:
                return base64.b64encode(img_file.read()).decode('utf-8')
        except Exception as e:
            logger.error(f"Error converting chart to base64: {str(e)}")
            return ""

    def generate_comparison_html(self):
        """Generate an HTML page comparing the latest interest rates from all banks"""
        try:
            conn = sqlite3.connect('austrian_banks.db')
            cursor = conn.cursor()
            
            # Get the latest entry for each bank
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
            
            # Convert rows to list of dictionaries for easier access
            rows_dict = []
            for row in rows:
                row_dict = dict(zip(column_names, row))
                rows_dict.append(row_dict)
            
            # Check if chart exists
            chart_exists = os.path.exists('interest_rate_chart.png')
            
            # Create HTML content
            html_content = f'''
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Konsumkredit Konditionenvergleich Österreich</title>
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
                    .chart-container {{
                        text-align: center;
                        margin-bottom: 30px;
                        padding: 20px;
                        background-color: #fafafa;
                        border-radius: 8px;
                        border: 1px solid #e0e0e0;
                    }}
                    .chart-container h2 {{
                        color: #2c3e50;
                        margin-bottom: 15px;
                        font-size: 1.3em;
                    }}
                    .chart-container img {{
                        max-width: 100%;
                        height: auto;
                        border-radius: 4px;
                        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
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
                        .chart-container {{
                            padding: 10px;
                            margin-bottom: 20px;
                        }}
                        .chart-container h2 {{
                            font-size: 1.1em;
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
                    <h1>Konsumkredit Konditionenvergleich Österreich</h1>
                    {f'''
                    <div class="chart-container">
                        <h2>Zinsentwicklung</h2>
                        <img src="data:image/png;base64,{self._get_chart_base64()}" alt="Interest Rate Development Chart">
                    </div>
                    ''' if chart_exists else ''}
                    <div class="table-responsive">
                        <table>
                            <thead>
                                <tr>
                                    <th>Parameter</th>
                                    {''.join(f'<th class="bank-name">{row["bank_name"].capitalize()}</th>' for row in rows_dict)}
                                </tr>
                            </thead>
                            <tbody>
                                <tr>
                                    <td class="parameter-name">Sollzinssatz</td>
                                    {''.join(f'<td class="value">{row["rate"]}</td>' for row in rows_dict)}
                                </tr>
                                <tr>
                                    <td class="parameter-name">Effektiver Jahreszins</td>
                                    {''.join(f'<td class="value">{row["effektiver_jahreszins"]}</td>' for row in rows_dict)}
                                </tr>
                                <tr>
                                    <td class="parameter-name">Nettokreditbetrag</td>
                                    {''.join(f'<td class="value">{row["nettokreditbetrag"]}</td>' for row in rows_dict)}
                                </tr>
                                <tr>
                                    <td class="parameter-name">Vertragslaufzeit</td>
                                    {''.join(f'<td class="value">{row["vertragslaufzeit"]}</td>' for row in rows_dict)}
                                </tr>
                                <tr>
                                    <td class="parameter-name">Gesamtbetrag</td>
                                    {''.join(f'<td class="value">{row["gesamtbetrag"]}</td>' for row in rows_dict)}
                                </tr>
                                <tr>
                                    <td class="parameter-name">Monatliche Rate</td>
                                    {''.join(f'<td class="value">{row["monatliche_rate"]}</td>' for row in rows_dict)}
                                </tr>
                            <tr>
                                <td class="parameter-name">Min. Kreditbetrag</td>
                                {''.join(f'<td class="value">{row["min_betrag"]}</td>' for row in rows_dict)}
                            </tr>
                            <tr>
                                <td class="parameter-name">Max. Kreditbetrag</td>
                                {''.join(f'<td class="value">{row["max_betrag"]}</td>' for row in rows_dict)}
                            </tr>
                            <tr>
                                <td class="parameter-name">Min. Laufzeit (Monate)</td>
                                {''.join(f'<td class="value">{row["min_laufzeit"]}</td>' for row in rows_dict)}
                            </tr>
                            <tr>
                                <td class="parameter-name">Max. Laufzeit (Monate)</td>
                                {''.join(f'<td class="value">{row["max_laufzeit"]}</td>' for row in rows_dict)}
                            </tr>
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
            
            # Write to file
            with open('bank_comparison.html', 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            logger.info("Comparison HTML file generated successfully")
            
            # Send email with the HTML content (DISABLED)
            # self.send_email(html_content)
            
        except Exception as e:
            logger.error(f"Error generating comparison HTML: {str(e)}")
        finally:
            conn.close()

    def send_email(self, html_content):
        """Send email with the bank comparison HTML content and screenshot attachments"""
        try:
            # Get email configuration from environment variables
            email_host = os.getenv('EMAIL_HOST')
            email_port = int(os.getenv('EMAIL_PORT', '587'))
            email_user = os.getenv('EMAIL_USER')
            email_password = os.getenv('EMAIL_PASSWORD')
            email_recipients = os.getenv('EMAIL_RECIPIENTS_KONSUMKREDIT', '').split(',')

            if not all([email_host, email_port, email_user, email_password, email_recipients]):
                logger.error("Missing email configuration in .env file")
                return

            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = "Aktuelle Konditionen Konsumredite in Österreich"
            msg['From'] = email_user
            msg['To'] = ', '.join(email_recipients)

            # Attach HTML content
            html_part = MIMEText(html_content, 'html')
            msg.attach(html_part)

            # Add attachments from screenshots folder (COMMENTED OUT)
            # screenshots_dir = './screenshots'
            # if os.path.exists(screenshots_dir):
            #     # Get all files from screenshots directory
            #     screenshot_files = glob.glob(os.path.join(screenshots_dir, '*'))
            #     
            #     for file_path in screenshot_files:
            #         if os.path.isfile(file_path):
            #             try:
            #                 # Get filename for attachment name
            #                 filename = os.path.basename(file_path)
            #                 
            #                 # Open the file
            #                 with open(file_path, 'rb') as attachment:
            #                     # Create MIME base object
            #                     part = MIMEBase('application', 'octet-stream')
            #                     part.set_payload(attachment.read())
            #                 
            #                 # Encode the attachment
            #                 encoders.encode_base64(part)
            #                 
            #                 # Add header
            #                 part.add_header(
            #                     'Content-Disposition',
            #                     f'attachment; filename= {filename}'
            #                 )
            #                 
            #                 # Attach to message
            #                 msg.attach(part)
            #                 
            #                 logger.info(f"Attached screenshot: {filename}")
            #                 
            #             except Exception as e:
            #                 logger.error(f"Error attaching {file_path}: {str(e)}")
            # else:
            #     logger.warning("Screenshots directory not found")

            # Send email
            with smtplib.SMTP(email_host, email_port) as server:
                server.starttls()
                server.login(email_user, email_password)
                server.send_message(msg)
            
            logger.info(f"Email sent successfully to {', '.join(email_recipients)}")
            
        except Exception as e:
            logger.error(f"Error sending email: {str(e)}")

    def run(self):
        """Run the scraper for all banks"""
        try:
            for bank_name in self.banks.keys():
                if self.enable_scraping[bank_name]:
                    logger.info(f"Starting scraping for {bank_name}")
                    self.scrape_interest_rates(bank_name)
                    time.sleep(2)  # Polite delay between banks
            
            self.export_to_excel()
            self.generate_interest_rate_chart()  # Generate chart after data scraping
            self.generate_comparison_html()
            
        except Exception as e:
            logger.error(f"Error during scraping: {str(e)}")
        finally:
            self.driver.quit()

if __name__ == "__main__":
    scraper = AustrianBankScraper()
    scraper.run() 
