# Austrian Bank Scraper - Refactored Version

A modular, extensible system for scraping Austrian bank interest rates with clean architecture and separation of concerns.

## 🏗️ Architecture Overview

The refactored code follows a modular design with clear separation of responsibilities:

### Core Components

1. **`LoanData`** - Data class for standardized loan information
2. **`WebDriverManager`** - Handles WebDriver lifecycle and configuration
3. **`DatabaseManager`** - Manages all database operations
4. **`BaseBankScraper`** - Abstract base class for all bank scrapers
5. **`BankScraperFactory`** - Factory pattern for creating bank scrapers
6. **`ReportGenerator`** - Generates HTML and Excel reports
7. **`EmailService`** - Handles email notifications
8. **`ScraperOrchestrator`** - Main coordinator for the scraping process

### Bank Scrapers

Each bank has its own dedicated scraper class:

- **`RaiffeisenScraper`** - Scrapes Raiffeisen Bank
- **`BawagScraper`** - Scrapes BAWAG Bank
- **`Bank99Scraper`** - Scrapes Bank99
- **`ErsteScraper`** - Scrapes Erste Bank

## 🚀 Usage

### Basic Usage

```python
# Run all enabled banks
orchestrator = ScraperOrchestrator()
orchestrator.run()

# Run specific banks only
orchestrator = ScraperOrchestrator(enabled_banks=['raiffeisen', 'bawag'])
orchestrator.run()
```

### Manual Scraping

```python
# Setup WebDriver
driver_manager = WebDriverManager()
driver_manager.setup_driver()

# Create and use a specific scraper
scraper = BankScraperFactory.create_scraper('raiffeisen', driver_manager)
loan_data = scraper.scrape_loan_data(loan_amount=15000, duration_months=48)

# Store data
db_manager = DatabaseManager()
db_manager.store_loan_data(loan_data)

# Cleanup
driver_manager.quit_driver()
```

## 🔧 Configuration

### Environment Variables

Create a `.env` file with the following variables:

```env
# Email Configuration
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USER=your-email@gmail.com
EMAIL_PASSWORD=your-app-password
EMAIL_RECIPIENTS=recipient1@email.com,recipient2@email.com
```

### Dependencies

Install required packages:

```bash
pip install -r requirements.txt
```

## 📈 Extensibility

### Adding a New Bank

1. **Create a new scraper class** extending `BaseBankScraper`:

```python
class NewBankScraper(BaseBankScraper):
    """Scraper for New Bank"""
    
    def get_bank_name(self) -> str:
        return 'newbank'
    
    def get_base_url(self) -> str:
        return 'https://newbank.at/loan-calculator'
    
    def scrape_loan_data(self, loan_amount: int = 10000, duration_months: int = 60) -> LoanData:
        """Scrape New Bank loan data"""
        logger.info(f"Scraping {self.bank_name} loan data")
        
        self.driver.get(self.base_url)
        
        # Your scraping logic here
        loan_data = LoanData(
            bank_name=self.bank_name,
            product_name='Representative Example',
            source_url=self.base_url
        )
        
        # Extract data and populate loan_data fields
        # ...
        
        self.take_screenshot()
        return loan_data
```

2. **Register the scraper** in `BankScraperFactory`:

```python
@staticmethod
def create_scraper(bank_name: str, driver_manager: WebDriverManager) -> BaseBankScraper:
    scrapers = {
        'raiffeisen': RaiffeisenScraper,
        'bawag': BawagScraper,
        'bank99': Bank99Scraper,
        'erste': ErsteScraper,
        'newbank': NewBankScraper  # Add your new scraper
    }
    # ...
```

3. **Enable the scraper** in the orchestrator:

```python
orchestrator = ScraperOrchestrator(enabled_banks=['raiffeisen', 'bawag', 'bank99', 'erste', 'newbank'])
```

### Adding New Loan Parameters

To add new loan parameters:

1. **Update the `LoanData` dataclass**:

```python
@dataclass
class LoanData:
    # ... existing fields ...
    new_parameter: Optional[str] = None
```

2. **Update the database schema** in `DatabaseManager.init_database()`:

```python
cursor.execute('''
    CREATE TABLE IF NOT EXISTS interest_rates (
        -- ... existing columns ...
        new_parameter TEXT
    )
''')
```

3. **Update the storage method** in `DatabaseManager.store_loan_data()`:

```python
cursor.execute('''
    INSERT INTO interest_rates (
        -- ... existing columns ...
        new_parameter
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
''', (
    # ... existing values ...
    loan_data.new_parameter
))
```

4. **Update the HTML report** in `ReportGenerator._create_html_content()`:

```python
parameters = [
    # ... existing parameters ...
    ('New Parameter', 'new_parameter')
]
```

### Custom Report Formats

Add new report formats by extending `ReportGenerator`:

```python
class CustomReportGenerator(ReportGenerator):
    
    def generate_pdf_report(self, filename: str = 'report.pdf'):
        """Generate PDF report"""
        # Implementation here
        pass
    
    def generate_json_report(self, filename: str = 'report.json'):
        """Generate JSON report"""
        data = self.db_manager.get_latest_data()
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2, default=str)
```

## 🔍 Key Improvements

### 1. **Separation of Concerns**
- Each class has a single responsibility
- Database operations are isolated
- Email functionality is separate from scraping

### 2. **Extensibility**
- Easy to add new banks via the factory pattern
- New parameters can be added without changing existing code
- New report formats can be added independently

### 3. **Maintainability**
- Clear inheritance hierarchy
- Consistent error handling
- Comprehensive logging
- Type hints for better code understanding

### 4. **Testability**
- Each component can be tested in isolation
- Dependency injection makes mocking easier
- Clear interfaces between components

### 5. **Configuration Management**
- Environment variables for sensitive data
- Centralized configuration
- Easy to modify behavior without code changes

## 🐛 Error Handling

The refactored code includes comprehensive error handling:

- **Individual bank failures** don't stop the entire process
- **Graceful degradation** when optional features fail
- **Detailed logging** for debugging
- **Screenshots** captured on errors for troubleshooting

## 📊 Data Flow

1. **Orchestrator** initializes all components
2. **WebDriver** is set up once and reused
3. **Each bank scraper** extracts data independently
4. **Database** stores all results
5. **Reports** are generated from stored data
6. **Email** sends results with attachments
7. **Cleanup** ensures proper resource management

## 🛠️ Development

### Running Tests

```bash
# Run individual scraper
python -c "
from austrian_bankscraper_refactored import *
orchestrator = ScraperOrchestrator(['raiffeisen'])
orchestrator.run()
"
```

### Debugging

Enable debug logging:

```python
logging.getLogger().setLevel(logging.DEBUG)
```

Screenshots are automatically saved to `./screenshots/` directory for debugging.

## 🔄 Migration from Original Code

The refactored code maintains the same functionality while providing:

- **Better organization** with clear class boundaries
- **Easier maintenance** with smaller, focused methods
- **Enhanced extensibility** for future requirements
- **Improved error handling** and logging
- **Type safety** with type hints

All original features are preserved while making the codebase more professional and maintainable.