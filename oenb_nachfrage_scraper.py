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

# Persisting the numeric chart data is best-effort: db_helper may be missing
# in some deployments, and this script must keep working screenshot-only if so.
try:
    from db_helper import save_oenb_series_data
    _DB_HELPER_AVAILABLE = True
except ImportError:
    _DB_HELPER_AVAILABLE = False

# JS extraction, tried against the two chart widget technologies we might be
# looking at (unverified against the live OeNB Shiny app - this dashboard was
# never inspected with real browser devtools from this environment; if the
# widget type turns out to be something else, this needs one more strategy
# added here, e.g. by opening devtools on the live page and running
# `document.getElementById(chartId)` to see what's rendered inside it).
_CHART_DATA_JS = """
return (function(chartId) {
    try {
        var el = document.getElementById(chartId);
        if (!el) return null;

        // Strategy 1: Plotly htmlwidget - the container itself or a
        // descendant carries class 'js-plotly-plot' and a `.data` array.
        // The raw x values are often just a sequential category index (not
        // a real date/quarter) - the actual period label (e.g. "2026 Q1",
        // "2025 H1") usually lives in the hover text instead, so prefer
        // trace.text/trace.hovertext over String(x) whenever it's present
        // and lines up 1:1 with the data points.
        var plotlyDiv = (el.classList && el.classList.contains('js-plotly-plot'))
            ? el : el.querySelector('.js-plotly-plot');
        if (plotlyDiv && plotlyDiv.data) {
            return plotlyDiv.data.map(function(trace) {
                var xRaw = trace.x || [];
                var labelSource = null;
                if (Array.isArray(trace.text) && trace.text.length === xRaw.length) {
                    labelSource = trace.text;
                } else if (Array.isArray(trace.hovertext) && trace.hovertext.length === xRaw.length) {
                    labelSource = trace.hovertext;
                }
                var x = labelSource ? labelSource.map(String) : xRaw.map(String);
                return {
                    name: trace.name || '',
                    x: x,
                    y: trace.y || []
                };
            });
        }

        // Strategy 2: Highcharts - find the chart whose render target is
        // this element (or is contained by it). Prefer each point's `name`
        // (Highcharts' categorical/label field) over the raw x value, for
        // the same reason as the Plotly branch above.
        if (window.Highcharts && Highcharts.charts) {
            for (var i = 0; i < Highcharts.charts.length; i++) {
                var c = Highcharts.charts[i];
                if (c && c.renderTo && (c.renderTo.id === chartId || el.contains(c.renderTo))) {
                    return c.series.map(function(s) {
                        var xData = s.xData || [];
                        var yData = s.yData || [];
                        var points = s.data || [];
                        var x = xData.map(function(xVal, idx) {
                            var point = points[idx];
                            if (point && point.name) {
                                return String(point.name);
                            }
                            return String(xVal);
                        });
                        return {
                            name: s.name || '',
                            x: x,
                            y: yData
                        };
                    });
                }
            }
        }

        return null;
    } catch (e) {
        return null;
    }
})(arguments[0]);
"""


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

    def extract_chart_data(self, chart_id: str) -> Optional[list]:
        """
        Best-effort extraction of the numeric series underlying a chart, so
        the HTML report can show a "last 5 periods" table under the
        screenshot (a screenshot's pixels can't be read back into numbers).

        Returns a list of {'name': str, 'points': [(period_label, value), ...]}
        (chronological order), or None if the widget type wasn't recognized
        or extraction failed - callers must treat that as "no data available",
        not as an error, and keep the screenshot-only flow working.
        """
        try:
            raw = self.driver.execute_script(_CHART_DATA_JS, chart_id)
        except Exception as e:
            print(f"[WARN] Could not execute chart-data extraction script for '{chart_id}': {e}")
            return None

        if not raw:
            print(f"[WARN] No recognizable chart widget data found for '{chart_id}' "
                  f"(extraction covers Plotly/Highcharts widgets only)")
            return None

        series = []
        for trace in raw:
            xs = trace.get('x') or []
            ys = trace.get('y') or []
            points = [(x, y) for x, y in zip(xs, ys) if y is not None]
            if points:
                series.append({'name': trace.get('name') or chart_id, 'points': points})

        # Diagnostic: if every period label is purely numeric, we likely fell
        # back to the raw x value instead of a real period label (trace.text/
        # hovertext/point.name weren't found or didn't line up) - the chart's
        # tooltip may use a different field name than the ones tried here.
        all_labels = [str(p[0]) for s in series for p in s['points']]
        if all_labels and all(label.strip().lstrip('-').isdigit() for label in all_labels):
            print(f"[WARN] Period labels for '{chart_id}' look purely numeric ({sorted(set(all_labels))[:5]}...) "
                  f"- likely couldn't find real period text on this chart. Check the chart's tooltip/hover "
                  f"markup in browser devtools for the actual field name and extend _CHART_DATA_JS.")

        return series or None

    def save_chart_data(self, chart_id: str, series: list) -> None:
        """Persist extracted series data via db_helper, if available."""
        if not _DB_HELPER_AVAILABLE:
            print("[WARN] db_helper not importable - skipping OeNB data-table persistence")
            return
        try:
            save_oenb_series_data(chart_id, series)
        except Exception as e:
            print(f"[WARN] Could not save OeNB series data for '{chart_id}': {e}")
    
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

            # Best-effort: also pull the underlying numeric series so the
            # HTML report can show a last-5-periods data table under each
            # screenshot. Never lets a failure here break the screenshot flow.
            for chart_id in screenshots:
                series = self.extract_chart_data(chart_id)
                if series:
                    self.save_chart_data(chart_id, series)

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

