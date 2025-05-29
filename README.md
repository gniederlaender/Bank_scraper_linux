# Austrian Bank Scraper (Linux Version)

A Python-based web scraper that collects and compares consumer loan interest rates from major Austrian banks. This version is specifically optimized for Linux systems, particularly ARM64 architecture.

## Features

- Scrapes interest rates and loan conditions from major Austrian banks:
  - Raiffeisen Bank
  - BAWAG
  - Bank99
  - Erste Bank
- Generates comparison tables in HTML format
- Exports data to Excel
- Sends email notifications with the latest comparison
- Supports headless browser operation
- Optimized for Linux/ARM64 architecture

## Prerequisites

- Python 3.8 or higher
- Firefox browser
- Geckodriver for Firefox
- Linux operating system (tested on ARM64)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/austrian-bank-scraper.git
cd austrian-bank-scraper
```

2. Install required Python packages:
```bash
pip install -r requirements.txt
```

3. Install Firefox and Geckodriver:
```bash
# For Ubuntu/Debian
sudo apt-get update
sudo apt-get install firefox

# Install Geckodriver
wget https://github.com/mozilla/geckodriver/releases/download/v0.33.0/geckodriver-v0.33.0-linux-aarch64.tar.gz
tar -xvzf geckodriver-v0.33.0-linux-aarch64.tar.gz
sudo mv geckodriver /usr/local/bin/
```

4. Create a `.env` file in the project root with the following content:
```env
# Email Configuration
EMAIL_HOST=smtp.gmx.net
EMAIL_PORT=587
EMAIL_SECURE=false
EMAIL_USER=your-email@gmx.net
EMAIL_PASSWORD=your-password
EMAIL_RECIPIENTS=recipient1@example.com,recipient2@example.com
```

## Usage

Run the scraper:
```bash
python austrian_bankscraper_linux.py
```

The script will:
1. Scrape interest rates from all configured banks
2. Generate an HTML comparison table
3. Export data to Excel
4. Send email notifications with the latest comparison

## Output Files

- `bank_comparison.html`: HTML table with current interest rates
- `austrian_banks_data.xlsx`: Excel file with detailed data
- `austrian_banks.db`: SQLite database with historical data
- `scraper.log`: Log file with execution details

## Project Structure

```
Bank_scraper_linux/
├── austrian_bankscraper_linux.py  # Main scraper script
├── requirements.txt               # Python dependencies
├── .env                          # Environment variables (not tracked in git)
├── README.md                     # This file
└── .gitignore                    # Git ignore file
```

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- Selenium WebDriver for browser automation
- Firefox and Geckodriver for headless browser support
- All the Austrian banks for providing their interest rate information 