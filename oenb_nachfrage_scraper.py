#!/usr/bin/env python3
"""
OeNB Wohnimmobilien-Dashboard Scraper
Scrapes the "Nachfrage" (Demand) tab and takes a screenshot of the chart
with id="demand_verah_durchschn_kreditsumme_chart"
"""

import os
import time
import signal
from pathlib import Path
from datetime import datetime
from typing import Optional

from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# Try to load dotenv if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def timeout_handler(signum, frame):
    """Signal handler for timeout"""
    raise TimeoutError("Operation timed out")


class OeNBNachfrageScraper:
    """Scraper for OeNB Wohnimmobilien-Dashboard Nachfrage tab"""
    
    def __init__(self, timeout: int = 60):
        self.timeout = timeout
        self.driver = None
        self.wait = None
        self.base_url = "https://oenb.shinyapps.io/wohnimmobilien_dashboard/"
        self.screenshots_dir = Path("screenshots")
        self.screenshots_dir.mkdir(exist_ok=True)
    
    def setup_driver(self) -> webdriver.Firefox:
        """Set up Firefox WebDriver with appropriate options"""
        os.environ['MOZ_HEADLESS'] = '1'
        os.environ['MOZ_DISABLE_CONTENT_SANDBOX'] = '1'
        
        options = Options()
        options.add_argument('--headless')
        options.set_preference('general.useragent.override', 
                              'Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/115.0')
        
        service = Service(
            executable_path='/usr/local/bin/geckodriver',
            log_output='geckodriver.log'
        )
        
        print("[INFO] Creating Firefox driver...")
        
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(self.timeout)
        
        try:
            self.driver = webdriver.Firefox(service=service, options=options)
            signal.alarm(0)
            print("[OK] Firefox driver created successfully!")
            self.wait = WebDriverWait(self.driver, 20)
            return self.driver
        except TimeoutError:
            print("[ERROR] Timeout: Firefox took too long to start")
            raise
        except Exception as e:
            signal.alarm(0)
            print(f"[ERROR] Error creating Firefox driver: {e}")
            raise
    
    def navigate_to_dashboard(self):
        """Navigate to the OeNB Wohnimmobilien-Dashboard"""
        print(f"[INFO] Navigating to: {self.base_url}")
        self.driver.get(self.base_url)
        
        # Wait for page to load
        print("[INFO] Waiting for page to load...")
        time.sleep(5)  # Give Shiny app time to initialize
    
    def click_nachfrage_tab(self):
        """Click on the 'Nachfrage' tab"""
        print("[INFO] Looking for 'Nachfrage' tab...")
        
        try:
            # Try multiple possible selectors for the tab
            # Shiny apps often use different structures
            selectors = [
                "//a[contains(text(), 'Nachfrage')]",
                "//li/a[contains(text(), 'Nachfrage')]",
                "//button[contains(text(), 'Nachfrage')]",
                "//*[@id='nav-tab-nachfrage']",
                "//a[@href='#nachfrage']",
            ]
            
            tab_found = False
            for selector in selectors:
                try:
                    tab = self.wait.until(
                        EC.element_to_be_clickable((By.XPATH, selector))
                    )
                    print(f"[OK] Found 'Nachfrage' tab using selector: {selector}")
                    tab.click()
                    tab_found = True
                    break
                except TimeoutException:
                    continue
            
            if not tab_found:
                # Try finding by partial link text
                try:
                    tab = self.wait.until(
                        EC.element_to_be_clickable((By.PARTIAL_LINK_TEXT, "Nachfrage"))
                    )
                    print("[OK] Found 'Nachfrage' tab using partial link text")
                    tab.click()
                    tab_found = True
                except TimeoutException:
                    pass
            
            if not tab_found:
                raise NoSuchElementException("Could not find 'Nachfrage' tab")
            
            # Wait for tab content to load
            print("[INFO] Waiting for 'Nachfrage' tab content to load...")
            time.sleep(5)  # Give Shiny time to render the tab content
            
        except Exception as e:
            print(f"[ERROR] Error clicking 'Nachfrage' tab: {e}")
            raise
    
    def wait_for_charts(self) -> dict:
        """Wait for both charts to load"""
        charts_status = {}
        
        chart_ids = [
            "demand_verah_durchschn_kreditsumme_chart",
            "demand_nkv_zins_chart"
        ]
        
        for chart_id in chart_ids:
            print(f"[INFO] Waiting for chart '{chart_id}' to appear...")
            try:
                chart = self.wait.until(
                    EC.presence_of_element_located((By.ID, chart_id))
                )
                print(f"[OK] Chart '{chart_id}' found!")
                charts_status[chart_id] = True
            except TimeoutException:
                print(f"[WARN] Chart '{chart_id}' not found within timeout period")
                charts_status[chart_id] = False
            except Exception as e:
                print(f"[ERROR] Error waiting for chart '{chart_id}': {e}")
                charts_status[chart_id] = False
        
        # Wait a bit more for charts to fully render
        if any(charts_status.values()):
            time.sleep(3)
        
        return charts_status
    
    def take_chart_screenshot(self, chart_id: str) -> Optional[Path]:
        """Take a screenshot of a specific chart"""
        try:
            # Find the chart element
            chart = self.driver.find_element(By.ID, chart_id)
            
            # Generate filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            # Use a simplified chart name for filename
            chart_name = chart_id.replace("demand_", "").replace("_chart", "")
            filename = f"oenb_nachfrage_{chart_name}_{timestamp}.png"
            filepath = self.screenshots_dir / filename
            
            # Take screenshot of the chart element
            print(f"[INFO] Taking screenshot of chart '{chart_id}'...")
            chart.screenshot(str(filepath))
            
            print(f"[OK] Screenshot saved: {filepath}")
            return filepath
            
        except NoSuchElementException:
            print(f"[ERROR] Chart element '{chart_id}' not found for screenshot")
            return None
        except Exception as e:
            print(f"[ERROR] Error taking screenshot of '{chart_id}': {e}")
            return None
    
    def take_all_chart_screenshots(self) -> dict:
        """Take screenshots of all charts"""
        screenshots = {}
        
        chart_ids = [
            "demand_verah_durchschn_kreditsumme_chart",
            "demand_nkv_zins_chart"
        ]
        
        for chart_id in chart_ids:
            screenshot_path = self.take_chart_screenshot(chart_id)
            if screenshot_path:
                screenshots[chart_id] = screenshot_path
        
        return screenshots
    
    def run(self) -> dict:
        """Run the complete scraping process
        
        Returns:
            dict: Dictionary mapping chart_id to screenshot filepath
        """
        screenshots = {}
        
        try:
            # Setup WebDriver
            self.setup_driver()
            
            # Navigate to dashboard
            self.navigate_to_dashboard()
            
            # Click Nachfrage tab
            self.click_nachfrage_tab()
            
            # Wait for charts
            charts_status = self.wait_for_charts()
            
            # Take screenshots of all available charts
            screenshots = self.take_all_chart_screenshots()
            
            if screenshots:
                print("[OK] Scraping process completed successfully")
            else:
                print("[WARN] No screenshots were captured")
            
            return screenshots
            
        except Exception as e:
            print(f"[ERROR] Error during scraping process: {e}")
            import traceback
            traceback.print_exc()
            return {}
        finally:
            self.quit_driver()
    
    def quit_driver(self):
        """Quit the WebDriver"""
        if self.driver:
            try:
                self.driver.quit()
                print("[INFO] WebDriver closed")
            except Exception as e:
                print(f"[WARN] Error closing WebDriver: {e}")
            finally:
                self.driver = None
                self.wait = None


def main():
    """Main entry point"""
    print("=" * 60)
    print("OeNB Wohnimmobilien-Dashboard Scraper")
    print("Nachfrage Tab - Chart Screenshots")
    print("=" * 60)
    print()
    
    scraper = OeNBNachfrageScraper(timeout=120)  # 2 minute timeout for Shiny app
    screenshots = scraper.run()
    
    if screenshots:
        print()
        print("=" * 60)
        print("✅ Scraping completed successfully!")
        print("📸 Screenshots saved:")
        for chart_id, filepath in screenshots.items():
            print(f"   - {chart_id}: {filepath}")
        print("=" * 60)
        return 0
    else:
        print()
        print("=" * 60)
        print("❌ Scraping failed!")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    exit(main())

