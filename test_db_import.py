"""
Test script to import mock data into the database
This validates the database structure and operations before integrating with the scraper
"""

from mock_test_data import get_mock_data
from db_helper import (
    create_database,
    save_scraping_data,
    get_all_runs,
    get_variations_for_run,
    print_database_summary
)


def test_import_mock_data():
    """Import mock data and verify database operations"""
    
    print("\n" + "="*60)
    print("TEST: Importing Mock Data to Database")
    print("="*60 + "\n")
    
    # Step 1: Create database
    print("Step 1: Creating database structure...")
    create_database()
    
    # Step 2: Import first dataset (500k, 30 years)
    print("\nStep 2: Importing Dataset 1 (500k, 30 years)...")
    data1 = get_mock_data(1)
    run_id_1 = save_scraping_data(data1)
    
    # Step 3: Import second dataset (300k, 25 years)
    print("\nStep 3: Importing Dataset 2 (300k, 25 years)...")
    data2 = get_mock_data(2)
    run_id_2 = save_scraping_data(data2)
    
    # Step 4: Verify data
    print("\n" + "="*60)
    print("VERIFICATION: Checking Database Contents")
    print("="*60 + "\n")
    
    # Get all runs
    all_runs = get_all_runs()
    print(f"Total runs in database: {len(all_runs)}")
    
    for run in all_runs:
        print(f"\n--- Run ID: {run['id']} ---")
        print(f"  Date: {run['scrape_date']}")
        print(f"  Kreditbetrag: €{run['kreditbetrag']:,.0f}")
        print(f"  Laufzeit: {run['laufzeit_jahre']} Jahre")
        print(f"  Kaufpreis: €{run['kaufpreis']:,.0f}")
        print(f"  Eigenmittel: €{run['eigenmittel']:,.0f}")
        
        # Get variations for this run
        variations = get_variations_for_run(run['id'])
        print(f"  Variations: {len(variations)}")
        
        # Show first 3 variations as sample
        for i, var in enumerate(variations[:3]):
            print(f"\n    Variation {i+1} (Verzinsung: {var['verzinsung_percent']}%):")
            print(f"      Rate: €{var['rate']:.2f}" if var['rate'] else "      Rate: N/A")
            print(f"      Zinssatz: {var['zinssatz']}")
            print(f"      Effektiver Zinssatz: {var['effektiver_zinssatz']}")
            print(f"      Kreditbetrag: €{var['kreditbetrag']:,.0f}" if var['kreditbetrag'] else "      Kreditbetrag: N/A")
    
    # Print summary
    print_database_summary()
    
    print("\n✅ Test completed successfully!")
    print(f"   - Database: /opt/Bankcomparison/austrian_banks_housing_loan.db")
    print(f"   - Runs imported: {len(all_runs)}")
    print(f"   - Total variations: {sum(len(get_variations_for_run(r['id'])) for r in all_runs)}")


def test_query_specific_run(run_id: int = 1):
    """Test querying a specific run and its variations"""
    
    print("\n" + "="*60)
    print(f"TEST: Query Specific Run (ID: {run_id})")
    print("="*60 + "\n")
    
    # Get run details
    runs = get_all_runs()
    run = next((r for r in runs if r['id'] == run_id), None)
    
    if not run:
        print(f"❌ Run ID {run_id} not found!")
        return
    
    print(f"Run Details:")
    print(f"  Kreditbetrag: €{run['kreditbetrag']:,.0f}")
    print(f"  Laufzeit: {run['laufzeit_jahre']} Jahre")
    print(f"  Kaufpreis: €{run['kaufpreis']:,.0f}")
    
    # Get variations
    variations = get_variations_for_run(run_id)
    print(f"\nVerzinsung Variations ({len(variations)} total):")
    print("-" * 60)
    
    for var in variations:
        if var['rate']:
            print(f"{var['verzinsung_percent']:2d}% | Rate: €{var['rate']:8.2f} | "
                  f"Zinssatz: {var['zinssatz']:30s} | "
                  f"Kreditbetrag: €{var['kreditbetrag']:,.0f}")
        else:
            print(f"{var['verzinsung_percent']:2d}% | No data available")


if __name__ == "__main__":
    import sys
    
    # Test 1: Import mock data
    test_import_mock_data()
    
    # Test 2: Query specific run
    if len(sys.argv) > 1:
        try:
            run_id = int(sys.argv[1])
            test_query_specific_run(run_id)
        except ValueError:
            print(f"Invalid run_id: {sys.argv[1]}")
    else:
        # Query the first run by default
        test_query_specific_run(1)

