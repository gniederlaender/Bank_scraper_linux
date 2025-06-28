from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.common.exceptions import WebDriverException
import time
import logging
import os
import subprocess
import socket
from urllib3.exceptions import MaxRetryError

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('browser_automation.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

def check_firefox_processes():
    try:
        result = subprocess.run(['ps', 'aux', '|', 'grep', 'firefox'], 
                              shell=True, capture_output=True, text=True)
        logger.debug(f"Running Firefox processes:\n{result.stdout}")
    except Exception as e:
        logger.error(f"Error checking Firefox processes: {e}")

def kill_firefox_processes():
    try:
        # Kill Firefox processes
        subprocess.run('pkill -f firefox', shell=True)
        # Kill geckodriver processes
        subprocess.run('pkill -f geckodriver', shell=True)
        time.sleep(1)  # Give processes time to terminate
    except Exception as e:
        logger.error(f"Error killing Firefox processes: {e}")

def check_firefox_installation():
    try:
        # Check Firefox version
        result = subprocess.run(['firefox', '--version'], 
                              capture_output=True, text=True)
        logger.info(f"Firefox version: {result.stdout.strip()}")
        
        # Check if Firefox is executable
        if not os.access('/usr/bin/firefox', os.X_OK):
            logger.error("Firefox is not executable")
            return False
            
        return True
    except Exception as e:
        logger.error(f"Error checking Firefox installation: {e}")
        return False

try:
    # Kill any existing Firefox processes
    kill_firefox_processes()
    
    # Check Firefox installation
    if not check_firefox_installation():
        raise Exception("Firefox installation check failed")
    
    logger.info("Initializing Firefox options")
    options = Options()
    
    # Basic options
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    
    # Set preferences
    options.set_preference('browser.tabs.remote.autostart', False)
    options.set_preference('browser.tabs.remote.autostart.2', False)
    options.set_preference('browser.sessionstore.resume_from_crash', False)
    options.set_preference('browser.sessionstore.max_tabs_undo', 0)
    options.set_preference('browser.sessionstore.max_windows_undo', 0)
    options.set_preference('browser.sessionstore.max_resumed_crashes', 0)
    
    # Additional preferences for stability
    options.set_preference('browser.startup.homepage', 'about:blank')
    options.set_preference('startup.homepage_welcome_url', 'about:blank')
    options.set_preference('startup.homepage_welcome_url.additional', 'about:blank')
    options.set_preference('browser.startup.homepage_override.mstone', 'ignore')
    options.set_preference('browser.startup.homepage_override.postreset', 'about:blank')
    
    logger.info("Setting up Firefox service")
    service = Service(
        executable_path='/usr/local/bin/geckodriver',
        log_output='geckodriver.log',
        log_level='trace'
    )
    
    logger.info("Starting Firefox WebDriver")
    check_firefox_processes()
    
    # Set connection timeout
    socket.setdefaulttimeout(30)
    
    driver = webdriver.Firefox(
        service=service,
        options=options
    )
    
    # Set timeouts after driver initialization
    logger.info("Setting timeouts")
    driver.set_page_load_timeout(30)
    driver.implicitly_wait(10)
    
    logger.info("Navigating to Google")
    driver.get('https://www.google.com')
    
    logger.info(f"Page title: {driver.title}")
    print(driver.title)
    
except WebDriverException as e:
    logger.error(f"WebDriver error occurred: {str(e)}", exc_info=True)
    check_firefox_processes()
    raise
except MaxRetryError as e:
    logger.error(f"Connection error occurred: {str(e)}", exc_info=True)
    check_firefox_processes()
    raise
except Exception as e:
    logger.error(f"An unexpected error occurred: {str(e)}", exc_info=True)
    check_firefox_processes()
    raise
finally:
    logger.info("Closing WebDriver")
    try:
        if 'driver' in locals():
            driver.quit()
    except Exception as e:
        logger.error(f"Error while closing WebDriver: {str(e)}")
    kill_firefox_processes()  # Ensure cleanup
    check_firefox_processes()
