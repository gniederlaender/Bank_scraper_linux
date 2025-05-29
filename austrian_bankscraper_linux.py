#!/usr/bin/env python3
import requests
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
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
                'sollzinssatz': r'Sollzinssatz\s*([\d,]+)\s*%\s*p\.a\.\s*fix',
                'effektiver_jahreszins': r'effektiver Jahreszins\s*([\d,]+)\s*%\s*p\.a\.',
                'nettokreditbetrag': r'Kreditbetrag von €\s*(\d{1,3}(?:\.\d{3})*)',
                'vertragslaufzeit': r'Laufzeit von\s*([\d]+)\s*Monate',
                'gesamtbetrag': r'Gesamtbetrag von €\s*(\d{1,3}(?:\.\d{3})*)',
                'monatliche_rate': r'€\s*([\d,.]+)\s*pro Monat'
            },
            'erste': {
                'sollzinssatz': 'interestRate',
                'effektiver_jahreszins': 'effectiveInterestRate',
                'nettokreditbetrag': 'startAmount',
                'vertragslaufzeit': 'startDuration',
                'gesamtbetrag': None,
                'monatliche_rate': 'installment'
            }
        }
        
        # Switch to enable/disable scraping for each bank
        self.enable_scraping = {
            'raiffeisen': True,
            'bawag': True,
            'bank99': True,
            'erste': True
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
                vertragslaufzeit INTEGER,
                effektiver_jahreszins TEXT,
                monatliche_rate TEXT,
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
                    
                    # Store the extracted fields in the database
                    self.store_interest_rate(bank_name, 'Representative Example', sollzinssatz, 'EUR', url, nettokreditbetrag, gesamtbetrag, vertragslaufzeit, effektiver_jahreszins, monatliche_rate, text)
                
                except Exception as e:
                    logger.error(f"Error processing Raiffeisen data: {str(e)}")
                    # Take a screenshot for debugging
                    self.driver.save_screenshot('raiffeisen_error.png')
                    raise
            
            elif bank_name == 'bawag':
                # Extract interest rate and fees from the specified element
                element = self.driver.find_element(By.CLASS_NAME, 'representative-calculation-example.calculation-text')
                text = element.text
                
                # Parse the text to extract specific fields using the mapping
                mapping = self.field_mapping[bank_name]
                sollzinssatz = re.search(rf"{mapping['sollzinssatz']}\s*([\d,]+%)\s*variabel", text).group(1) if re.search(rf"{mapping['sollzinssatz']}\s*([\d,]+%)\s*variabel", text) else None
                effektiver_jahreszins = re.search(rf"{mapping['effektiver_jahreszins']}\s*([\d,]+%)\s*p\.a\.", text).group(1) if re.search(rf"{mapping['effektiver_jahreszins']}\s*([\d,]+%)\s*p\.a\.", text) else None
                nettokreditbetrag = re.search(rf"{mapping['nettokreditbetrag']}\s*([\d,.]+)\s*Euro", text).group(1) if re.search(rf"{mapping['nettokreditbetrag']}\s*([\d,.]+)\s*Euro", text) else None
                vertragslaufzeit = re.search(rf"{mapping['vertragslaufzeit']}\s*([\d]+)\s*Monate", text).group(1) if re.search(rf"{mapping['vertragslaufzeit']}\s*([\d]+)\s*Monate", text) else None
                gesamtbetrag = re.search(rf"{mapping['gesamtbetrag']}\s*([\d,.]+)\s*Euro", text).group(1) if re.search(rf"{mapping['gesamtbetrag']}\s*([\d,.]+)\s*Euro", text) else None
                monatliche_rate = re.search(rf"{mapping['monatliche_rate']}\s*([\d,.]+)\s*Euro", text).group(1) if re.search(rf"{mapping['monatliche_rate']}\s*([\d,.]+)\s*Euro", text) else None
                
                # Store the extracted fields in the database
                self.store_interest_rate(bank_name, 'Representative Example', sollzinssatz, 'EUR', url, nettokreditbetrag, gesamtbetrag, vertragslaufzeit, effektiver_jahreszins, monatliche_rate, text)
            
            elif bank_name == 'bank99':
                # Wait for the specific element to be present
                element = self.wait.until(EC.presence_of_element_located((
                    By.CSS_SELECTOR, 
                    "h2[id*='reprasentatives-beispiel'] + div.copy p"
                )))
                text = element.text
                logger.info(f"Extracted text: {text}")
                
                # Parse the text to extract specific fields using the mapping
                mapping = self.field_mapping[bank_name]
                sollzinssatz = re.search(mapping['sollzinssatz'], text).group(1) if re.search(mapping['sollzinssatz'], text) else None
                effektiver_jahreszins = re.search(mapping['effektiver_jahreszins'], text).group(1) if re.search(mapping['effektiver_jahreszins'], text) else None
                nettokreditbetrag = re.search(mapping['nettokreditbetrag'], text).group(1) if re.search(mapping['nettokreditbetrag'], text) else None
                vertragslaufzeit = re.search(mapping['vertragslaufzeit'], text).group(1) if re.search(mapping['vertragslaufzeit'], text) else None
                gesamtbetrag = re.search(mapping['gesamtbetrag'], text).group(1) if re.search(mapping['gesamtbetrag'], text) else None
                monatliche_rate = re.search(mapping['monatliche_rate'], text).group(1) if re.search(mapping['monatliche_rate'], text) else None
                
                # Store the extracted fields in the database
                self.store_interest_rate(bank_name, 'Representative Example', sollzinssatz, 'EUR', url, nettokreditbetrag, gesamtbetrag, vertragslaufzeit, effektiver_jahreszins, monatliche_rate, text)
            
            elif bank_name == 'erste':
                # Fetch JSON data directly from the API
                api_url = self.banks[bank_name]['interest_rates_url']
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                }
                response = requests.get(api_url, headers=headers, verify=False)
                response.raise_for_status()
                data = response.json()
                mapping = self.field_mapping[bank_name]
                sollzinssatz = data.get(mapping['sollzinssatz'])
                effektiver_jahreszins = data.get(mapping['effektiver_jahreszins'])
                nettokreditbetrag = data.get(mapping['nettokreditbetrag'])
                vertragslaufzeit = data.get(mapping['vertragslaufzeit'])
                gesamtbetrag = None
                monatliche_rate = data.get(mapping['monatliche_rate'])
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
                    str(data)
                )
            
        except Exception as e:
            logger.error(f"Error scraping interest rates for {bank_name}: {str(e)}")
            # Take a screenshot for debugging
            try:
                self.driver.save_screenshot(f"{bank_name}_error_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
            except:
                pass

    def store_interest_rate(self, bank_name, product_name, rate, currency, source_url, nettokreditbetrag=None, gesamtbetrag=None, vertragslaufzeit=None, effektiver_jahreszins=None, monatliche_rate=None, full_text=None):
        """Store interest rate in database"""
        conn = sqlite3.connect('austrian_banks.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO interest_rates (bank_name, product_name, rate, currency, date_scraped, source_url, nettokreditbetrag, gesamtbetrag, vertragslaufzeit, effektiver_jahreszins, monatliche_rate, full_text)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (bank_name, product_name, rate, currency, datetime.now(), source_url, nettokreditbetrag, gesamtbetrag, vertragslaufzeit, effektiver_jahreszins, monatliche_rate, full_text))
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
            
            # Create HTML content
            html_content = f'''
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
                    table {{
                        width: 100%;
                        border-collapse: collapse;
                        margin-bottom: 20px;
                    }}
                    th, td {{
                        padding: 12px;
                        text-align: left;
                        border-bottom: 1px solid #ddd;
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
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>Austrian Banks Interest Rate Comparison</h1>
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
                        </tbody>
                    </table>
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
            
            # Send email with the HTML content
            self.send_email(html_content)
            
        except Exception as e:
            logger.error(f"Error generating comparison HTML: {str(e)}")
        finally:
            conn.close()

    def send_email(self, html_content):
        """Send email with the bank comparison HTML content"""
        try:
            # Get email configuration from environment variables
            email_host = os.getenv('EMAIL_HOST')
            email_port = int(os.getenv('EMAIL_PORT', '587'))
            email_user = os.getenv('EMAIL_USER')
            email_password = os.getenv('EMAIL_PASSWORD')
            email_recipients = os.getenv('EMAIL_RECIPIENTS', '').split(',')

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
            self.generate_comparison_html()
            
        except Exception as e:
            logger.error(f"Error during scraping: {str(e)}")
        finally:
            self.driver.quit()

if __name__ == "__main__":
    scraper = AustrianBankScraper()
    scraper.run() 