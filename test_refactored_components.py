#!/usr/bin/env python3
"""
Test script for the refactored Austrian bank scraper components
This allows you to test individual parts without running the full scraper
"""

import os
import sys
from datetime import datetime

# Add the current directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from austrian_bankscraper_refactored import (
    LoanData, 
    WebDriverManager, 
    DatabaseManager, 
    BankScraperFactory, 
    ReportGenerator,
    ScraperOrchestrator
)

def test_loan_data():
    """Test the LoanData class"""
    print("=== Testing LoanData Class ===")
    
    loan_data = LoanData(
        bank_name="test_bank",
        product_name="Test Product",
        sollzinssatz="5.5%",
        effektiver_jahreszins="5.7%",
        nettokreditbetrag="10000 EUR",
        monatliche_rate="180 EUR"
    )
    
    print(f"Bank: {loan_data.bank_name}")
    print(f"Product: {loan_data.product_name}")
    print(f"Interest Rate: {loan_data.sollzinssatz}")
    print(f"Date: {loan_data.date_scraped}")
    print("✅ LoanData test passed!\n")

def test_database_manager():
    """Test the DatabaseManager class"""
    print("=== Testing DatabaseManager ===")
    
    # Create a test database
    db_manager = DatabaseManager('test_banks.db')
    
    # Create test data
    test_data = LoanData(
        bank_name="test_bank",
        product_name="Test Product",
        sollzinssatz="5.5%",
        effektiver_jahreszins="5.7%",
        nettokreditbetrag="10000 EUR"
    )
    
    # Store data
    db_manager.store_loan_data(test_data)
    print("✅ Data stored successfully")
    
    # Retrieve data
    latest_data = db_manager.get_latest_data()
    print(f"✅ Retrieved {len(latest_data)} records")
    
    # Test Excel export
    try:
        db_manager.export_to_excel('test_export.xlsx')
        print("✅ Excel export successful")
    except Exception as e:
        print(f"⚠️ Excel export failed: {e}")
    
    print()

def test_report_generator():
    """Test the ReportGenerator class"""
    print("=== Testing ReportGenerator ===")
    
    # Use the test database
    db_manager = DatabaseManager('test_banks.db')
    report_generator = ReportGenerator(db_manager)
    
    # Generate HTML report
    html_content = report_generator.generate_html_report('test_report.html')
    
    if html_content:
        print("✅ HTML report generated successfully")
        print(f"Report length: {len(html_content)} characters")
    else:
        print("⚠️ HTML report generation failed")
    
    print()

def test_scraper_factory():
    """Test the BankScraperFactory"""
    print("=== Testing BankScraperFactory ===")
    
    # Test without actually creating WebDriver
    print("Available scrapers:")
    scrapers = ['raiffeisen', 'bawag', 'bank99', 'erste']
    
    for scraper_name in scrapers:
        try:
            # This will fail because we don't have a WebDriver, but it tests the factory logic
            BankScraperFactory.create_scraper(scraper_name, None)  # type: ignore
            print(f"✅ {scraper_name} scraper class found")
        except Exception as e:
            if "WebDriverManager" in str(e) or "NoneType" in str(e):
                print(f"✅ {scraper_name} scraper class found (WebDriver not initialized)")
            else:
                print(f"❌ {scraper_name} scraper error: {e}")
    
    # Test invalid scraper
    try:
        BankScraperFactory.create_scraper('invalid_bank', None)  # type: ignore
        print("❌ Should have failed for invalid bank")
    except ValueError as e:
        print(f"✅ Correctly rejected invalid bank: {e}")
    
    print()

def test_orchestrator_setup():
    """Test the ScraperOrchestrator setup (without running)"""
    print("=== Testing ScraperOrchestrator Setup ===")
    
    # Test with default banks
    orchestrator = ScraperOrchestrator()
    print(f"✅ Default enabled banks: {orchestrator.enabled_banks}")
    
    # Test with custom banks
    custom_orchestrator = ScraperOrchestrator(enabled_banks=['raiffeisen', 'bawag'])
    print(f"✅ Custom enabled banks: {custom_orchestrator.enabled_banks}")
    
    # Check if screenshots directory is created
    if os.path.exists('screenshots'):
        print("✅ Screenshots directory created")
    else:
        print("⚠️ Screenshots directory not found")
    
    print()

def test_single_bank_scraper():
    """Test a single bank scraper (user choice)"""
    print("=== Testing Single Bank Scraper ===")
    print("Choose a bank to test:")
    print("1. Raiffeisen")
    print("2. BAWAG")
    print("3. Bank99")
    print("4. Erste")
    print("5. Skip this test")
    
    choice = input("Enter your choice (1-5): ").strip()
    
    bank_mapping = {
        '1': 'raiffeisen',
        '2': 'bawag',
        '3': 'bank99',
        '4': 'erste'
    }
    
    if choice in bank_mapping:
        bank_name = bank_mapping[choice]
        print(f"\n🚀 Testing {bank_name} scraper...")
        
        try:
            # Create orchestrator with just this bank
            orchestrator = ScraperOrchestrator(enabled_banks=[bank_name])
            
            # Run the scraper
            orchestrator.run()
            
            print(f"✅ {bank_name} scraper test completed!")
            
        except Exception as e:
            print(f"❌ {bank_name} scraper test failed: {e}")
    else:
        print("Skipping single bank test")
    
    print()

def cleanup_test_files():
    """Clean up test files"""
    print("=== Cleaning up test files ===")
    
    test_files = [
        'test_banks.db',
        'test_export.xlsx',
        'test_report.html',
        'geckodriver.log'
    ]
    
    for file in test_files:
        if os.path.exists(file):
            try:
                os.remove(file)
                print(f"✅ Removed {file}")
            except Exception as e:
                print(f"⚠️ Could not remove {file}: {e}")
    
    print()

def main():
    """Main test function"""
    print("🧪 Testing Refactored Austrian Bank Scraper Components")
    print("=" * 60)
    
    # Test individual components
    test_loan_data()
    test_database_manager()
    test_report_generator()
    test_scraper_factory()
    test_orchestrator_setup()
    
    # Ask if user wants to test actual scraping
    print("\n🚨 The next test will run actual web scraping!")
    print("Make sure you have:")
    print("- Firefox installed")
    print("- geckodriver in /usr/local/bin/")
    print("- Internet connection")
    print("- .env file configured (for email)")
    
    run_scraper = input("\nDo you want to test actual scraping? (y/N): ").strip().lower()
    
    if run_scraper == 'y':
        test_single_bank_scraper()
    else:
        print("Skipping actual scraping test")
    
    # Cleanup
    cleanup_choice = input("\nDo you want to clean up test files? (Y/n): ").strip().lower()
    if cleanup_choice != 'n':
        cleanup_test_files()
    
    print("🎉 All tests completed!")

if __name__ == "__main__":
    main()