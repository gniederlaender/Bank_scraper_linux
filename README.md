# Austrian Bank Scraper (Linux Version)

A comprehensive Python-based web scraper system that collects and compares loan interest rates from Austrian financial institutions. This system scrapes both **housing loans (Wohnkredit)** and **consumer loans (Konsumkredit)**, generates interactive HTML reports with charts, and delivers automated email notifications.

## Features

### Dual Loan Type Support
- **Housing Loans (Wohnkredit)**: Scrapes Durchblicker.at for housing loan rates with multiple Fixierung (fixed interest period) variations
- **Consumer Loans (Konsumkredit)**: Scrapes interest rates from major Austrian banks:
  - Raiffeisen Bank
  - BAWAG
  - Bank99
  - Erste Bank

### Data Processing & Visualization
- Generates interactive HTML comparison reports with Plotly charts
- Creates PNG chart images for email attachments
- SQLite database storage with automatic view creation
- Historical data tracking with timestamps
- Advanced data parsing (German number/date formats)

### Automation & Delivery
- Sends automated email reports with HTML content and chart attachments
- Fully automated workflow via bash scripts
- Deploys reports to web server (optional)
- Comprehensive logging and error handling

### Browser Automation
- Uses Playwright for housing loan scraping (Durchblicker.at)
- Uses Selenium with Firefox for consumer loan scraping
- Supports headless browser operation
- Optimized for Linux/ARM64 architecture

## Prerequisites

- Python 3.8 or higher
- Firefox browser and Geckodriver (for consumer loan scraping)
- Playwright (for housing loan scraping via Durchblicker.at)
- Linux operating system (tested on ARM64)
- Web server directory for report deployment (optional)

## Installation

### 1. Clone the Repository
```bash
git clone https://github.com/gniederlaender/Bank_scraper_linux.git
cd Bank_scraper_linux
```

### 2. Install Python Dependencies
```bash
# Install main dependencies
pip install -r requirements.txt

# Install chart dependencies
pip install -r requirements_chart.txt

# Install Playwright browsers
playwright install firefox
```

### 3. Install System Dependencies (Ubuntu/Debian)
```bash
# Install Firefox
sudo apt-get update
sudo apt-get install firefox

# Install Geckodriver for ARM64
wget https://github.com/mozilla/geckodriver/releases/download/v0.33.0/geckodriver-v0.33.0-linux-aarch64.tar.gz
tar -xvzf geckodriver-v0.33.0-linux-aarch64.tar.gz
sudo mv geckodriver /usr/local/bin/
```

### 4. Configure Environment Variables
Create a `.env` file in the project root:
```env
# Email Configuration
EMAIL_HOST=smtp.gmx.net
EMAIL_PORT=587
EMAIL_USER=your-email@gmx.net
EMAIL_PASSWORD=your-password

# Recipients (separate for each loan type)
EMAIL_RECIPIENTS_WOHNKREDIT=recipient1@example.com
EMAIL_RECIPIENTS_KONSUMKREDIT=recipient2@example.com

# Database Paths (optional, uses defaults if not specified)
HOUSING_LOAN_DB_PATH=austrian_banks_housing_loan.db
CONSUMER_LOAN_DB_PATH=austrian_banks.db

# Base Directory (optional)
BANKCOMPARISON_BASE_DIR=/opt/Bankcomparison
SCREENSHOTS_DIR=/opt/Bankcomparison/screenshots

# Web Server Deployment (optional)
WEB_ROOT=/var/www/xxx
```

## Usage

### Full Workflow (Recommended)
Run the complete scraper workflow for both loan types:
```bash
./run_full_scraper.sh
```

This automated script will:
1. Scrape housing loan data from Durchblicker.at
2. Create database views for housing loan charts
3. Generate interactive HTML reports with charts
4. Deploy reports to web server (if configured)
5. Send email notifications for housing loans
6. Scrape consumer loan data from Austrian banks
7. Create database views for consumer loan charts
8. Generate interactive HTML reports with charts
9. Deploy reports to web server (if configured)
10. Send email notifications for consumer loans

### Individual Components

#### Housing Loans Only
```bash
# Run scraper
python3 test_durchblicker.py

# Create database views
python3 create_housing_loan_view.py

# Generate HTML report
python3 generate_housing_loan_html.py

# Send email
python3 send_email_report.py bank_comparison_housing_loan_durchblicker_email.html --type wohnkredit
```

#### Consumer Loans Only
```bash
# Run scraper
python3 austrian_bankscraper_linux.py

# Create database views
python3 create_consumer_loan_view.py

# Generate HTML report
python3 generate_consumer_loan_html.py

# Send email
python3 send_email_report.py bank_comparison_consumer_loan_email.html --type konsumkredit
```

## Output Files

### Housing Loan Files
- `bank_comparison_housing_loan_durchblicker.html`: Interactive HTML report with Plotly charts
- `bank_comparison_housing_loan_durchblicker_email.html`: Email-friendly HTML version
- `housing_loan_chart.png`: PNG chart image for email attachments
- `austrian_banks_housing_loan.db`: SQLite database with historical housing loan data

### Consumer Loan Files
- `bank_comparison_consumer_loan.html`: Interactive HTML report with Plotly charts
- `bank_comparison_consumer_loan_email.html`: Email-friendly HTML version
- `consumer_loan_chart.png`: PNG chart image for email attachments
- `austrian_banks.db` or `austrian_banks_consumer_loan.db`: SQLite database with historical consumer loan data

### Log Files
- `scraper.log`: Consumer loan scraper execution logs
- `email_report.log`: Email sending operation logs

## Project Structure

```
Bank_scraper_linux/
├── Scrapers
│   ├── test_durchblicker.py                    # Housing loan scraper (Playwright)
│   └── austrian_bankscraper_linux.py           # Consumer loan scraper (Selenium)
│
├── Database Management
│   ├── db_helper.py                            # Database operations & utilities
│   ├── create_housing_loan_view.py             # Housing loan database views
│   └── create_consumer_loan_view.py            # Consumer loan database views
│
├── Report Generation
│   ├── generate_housing_loan_html.py           # Housing loan HTML + charts
│   └── generate_consumer_loan_html.py        # Consumer loan HTML + charts
│
├── Email & Automation
│   ├── send_email_report.py                   # Email report sender
│   └── run_full_scraper.sh                    # Complete workflow orchestrator
│
├── Dependencies
│   ├── requirements.txt                        # Python packages (Selenium, etc.)
│   └── requirements_chart.txt                 # Chart packages (Plotly, Matplotlib)
│
├── Databases
│   ├── austrian_banks_housing_loan.db         # Housing loan data
│   └── austrian_banks.db                       # Consumer loan data
│
└── Configuration
    ├── .env                                    # Environment variables (not in git)
    ├── .gitignore
    └── README.md                               # This file
```

## Database Schema

### Housing Loan Database (`austrian_banks_housing_loan.db`)

**Tables:**
- `scraping_runs`: Stores metadata for each scraping session (loan amount, term, household info, etc.)
- `fixierung_variations`: Stores loan offers for different fixed interest periods (0, 5, 10, 15, 20, 25, 30 years)
- `loan_offers`: Stores user-submitted loan offers from PDF documents

**Views:**
- `housing_loan_chart_ready`: Prepared data view with parsed numeric values for charting

### Consumer Loan Database (`austrian_banks.db`)

**Tables:**
- `interest_rates`: Stores interest rates and loan conditions from bank scraping sessions

**Views:**
- `consumer_loan_chart_ready`: Prepared data view with parsed numeric values for charting

## Scheduling & Automation

### Cron Job Setup
To run the scraper on a schedule (e.g., daily at 6 AM):

```bash
# Edit crontab
crontab -e

# Add this line for daily execution at 6 AM
0 6 * * * cd /opt/Bankcomparison && /path/to/venv/bin/python3 /opt/Bankcomparison/run_full_scraper.sh >> /var/log/bank_scraper.log 2>&1
```

### Manual Execution
For one-time runs:
```bash
cd /opt/Bankcomparison
./run_full_scraper.sh
```

## Technical Details

### Data Parsing
- **German Number Format**: Automatically converts `"2,650%"` → `2.65`, `"1.234,56 €"` → `1234.56`
- **German Date Format**: Parses `"DD.MM.YYYY"` to datetime objects
- **Currency Handling**: Removes currency symbols and converts to floats

### Browser Automation
- **Playwright**: Used for housing loan scraping (Durchblicker.at) with advanced DOM manipulation
- **Selenium**: Used for consumer loan scraping with Firefox/Geckodriver
- **Headless Mode**: Both scrapers run in headless mode for server environments

### Chart Generation
- **Plotly**: Interactive HTML charts with filters, legends, and zoom capabilities
- **Matplotlib**: Static PNG charts for email attachments
- **Chart Features**: 
  - Date-based time series
  - Multiple loan parameters (fixed/variable rates, effective rates)
  - Bank/provider comparison
  - Responsive design for mobile devices

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## Troubleshooting

### Common Issues

**Firefox/Geckodriver Issues**
```bash
# Verify Geckodriver installation
which geckodriver
geckodriver --version

# Install Firefox
sudo apt-get update && sudo apt-get install firefox
```

**Playwright Installation Issues**
```bash
# Reinstall Playwright browsers
playwright install firefox
playwright install --help
```

**Email Sending Fails**
- Verify `.env` file has correct email credentials
- Check firewall allows SMTP connections (port 587)
- Ensure EMAIL_RECIPIENTS environment variable is set

**Database Errors**
- Ensure SQLite write permissions on database files
- Check database file paths in `.env`
- Run `create_housing_loan_view.py` and `create_consumer_loan_view.py` to recreate views

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- **Playwright** for robust browser automation
- **Selenium** and **Firefox/Geckodriver** for web scraping
- **Plotly** for interactive chart generation
- **Matplotlib** for static chart rendering
- **Durchblicker.at** for providing loan comparison data
- Austrian banks (Raiffeisen, BAWAG, Bank99, Erste Bank) for loan rate information 