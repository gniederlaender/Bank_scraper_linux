#!/usr/bin/env python3
"""
Test Script for Database Chart Generation
Tests database connection, data extraction, and chart creation.
"""

import os
import sys
import sqlite3
from database_chart_generator import DatabaseChartGenerator

def test_database_connection(db_path):
    """Test basic database connection and structure"""
    print(f"🔍 Testing database: {db_path}")
    print("-" * 40)
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get table names
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        
        print(f"✓ Connected successfully")
        print(f"✓ Found {len(tables)} tables: {', '.join(tables)}")
        
        # Check interest_rates table specifically
        if 'interest_rates' in tables:
            cursor.execute("SELECT COUNT(*) FROM interest_rates")
            count = cursor.fetchone()[0]
            print(f"✓ interest_rates table has {count} records")
            
            # Check for data with effective interest rates
            cursor.execute("""
                SELECT COUNT(*) FROM interest_rates 
                WHERE effektiver_jahreszins IS NOT NULL 
                AND effektiver_jahreszins != ''
            """)
            rate_count = cursor.fetchone()[0]
            print(f"✓ {rate_count} records have effective interest rates")
            
            # Show sample data
            cursor.execute("""
                SELECT bank_name, effektiver_jahreszins, date_scraped 
                FROM interest_rates 
                WHERE effektiver_jahreszins IS NOT NULL 
                AND effektiver_jahreszins != ''
                LIMIT 5
            """)
            samples = cursor.fetchall()
            print(f"✓ Sample data:")
            for sample in samples:
                print(f"   {sample[0]}: {sample[1]} ({sample[2]})")
        else:
            print("✗ No 'interest_rates' table found")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def test_chart_generation():
    """Test the chart generation process"""
    print("\n🎨 Testing Chart Generation")
    print("-" * 40)
    
    # Find available databases
    db_files = ['austrian_banks.db', 'austrian_banks_housing_loan.db']
    available_dbs = [db for db in db_files if os.path.exists(db)]
    
    if not available_dbs:
        print("✗ No database files found!")
        return False
    
    # Test with each available database
    for db_path in available_dbs:
        print(f"\n📊 Testing chart generation with {db_path}")
        
        try:
            generator = DatabaseChartGenerator(db_path)
            
            # Test database analysis
            if generator.analyze_database():
                print("✓ Database analysis successful")
                
                # Test data extraction
                chart_data = generator.extract_chart_data()
                if chart_data:
                    print(f"✓ Data extraction successful - {len(chart_data)} banks")
                    
                    # Test chart creation
                    chart_file = f"test_chart_{db_path.replace('.db', '')}.png"
                    if generator.create_interest_rate_chart(chart_data, chart_file):
                        print(f"✓ Chart creation successful - saved as {chart_file}")
                        
                        # Show summary
                        generator.create_summary_statistics(chart_data)
                    else:
                        print("✗ Chart creation failed")
                else:
                    print("✗ Data extraction failed")
            else:
                print("✗ Database analysis failed")
                
        except Exception as e:
            print(f"✗ Error during chart generation: {e}")
        
        finally:
            generator.analyzer.close()

def main():
    """Main test function"""
    print("🧪 Database Chart Generator Test Suite")
    print("=" * 50)
    
    # Test database connections
    db_files = ['austrian_banks.db', 'austrian_banks_housing_loan.db']
    
    for db_file in db_files:
        if os.path.exists(db_file):
            test_database_connection(db_file)
        else:
            print(f"⚠️  Database file not found: {db_file}")
    
    # Test chart generation
    test_chart_generation()
    
    print("\n" + "=" * 50)
    print("🏁 Test completed!")

if __name__ == "__main__":
    main()
