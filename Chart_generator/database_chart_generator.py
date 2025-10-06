#!/usr/bin/env python3
"""
Database Chart Generator
Extracts data from austrian_banks.db and creates interest rate development charts.
"""

import sqlite3
import json
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from typing import List, Dict, Tuple, Optional
import os

class DatabaseAnalyzer:
    """Analyzes the SQLite database structure and content"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = None
        
    def connect(self):
        """Connect to the database"""
        try:
            self.conn = sqlite3.connect(self.db_path)
            print(f"✓ Connected to database: {self.db_path}")
            return True
        except Exception as e:
            print(f"✗ Error connecting to database: {e}")
            return False
    
    def get_table_info(self) -> Dict:
        """Get information about all tables in the database"""
        if not self.conn:
            return {}
        
        cursor = self.conn.cursor()
        
        # Get all table names
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        
        table_info = {}
        for table in tables:
            # Get column information
            cursor.execute(f"PRAGMA table_info({table})")
            columns = cursor.fetchall()
            
            # Get row count
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            row_count = cursor.fetchone()[0]
            
            # Get sample data
            cursor.execute(f"SELECT * FROM {table} LIMIT 3")
            sample_data = cursor.fetchall()
            
            table_info[table] = {
                'columns': [col[1] for col in columns],
                'row_count': row_count,
                'sample_data': sample_data
            }
        
        return table_info
    
    def get_interest_rate_data(self) -> pd.DataFrame:
        """Extract interest rate data from the database"""
        if not self.conn:
            return pd.DataFrame()
        
        query = """
        SELECT 
            bank_name,
            product_name,
            effektiver_jahreszins,
            date_scraped,
            nettokreditbetrag,
            vertragslaufzeit,
            source_url
        FROM interest_rates 
        WHERE effektiver_jahreszins IS NOT NULL 
        AND effektiver_jahreszins != ''
        ORDER BY date_scraped, bank_name
        """
        
        try:
            df = pd.read_sql_query(query, self.conn)
            print(f"✓ Extracted {len(df)} interest rate records")
            return df
        except Exception as e:
            print(f"✗ Error extracting data: {e}")
            return pd.DataFrame()
    
    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()

class DatabaseChartGenerator:
    """Generates charts from database data"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.analyzer = DatabaseAnalyzer(db_path)
        
    def analyze_database(self):
        """Analyze the database structure and content"""
        print("="*60)
        print("DATABASE ANALYSIS")
        print("="*60)
        
        if not self.analyzer.connect():
            return False
        
        # Get table information
        table_info = self.analyzer.get_table_info()
        
        print(f"\nFound {len(table_info)} tables:")
        for table_name, info in table_info.items():
            print(f"\n📊 Table: {table_name}")
            print(f"   Rows: {info['row_count']}")
            print(f"   Columns: {', '.join(info['columns'])}")
            
            if info['sample_data']:
                print("   Sample data:")
                for i, row in enumerate(info['sample_data'][:2]):  # Show first 2 rows
                    print(f"     Row {i+1}: {row[:3]}...")  # Show first 3 columns
        
        return True
    
    def extract_chart_data(self) -> Dict:
        """Extract data suitable for charting"""
        if not self.analyzer.connect():
            return {}
        
        df = self.analyzer.get_interest_rate_data()
        if df.empty:
            print("✗ No data found for charting")
            return {}
        
        # Clean and process the data
        df['date_scraped'] = pd.to_datetime(df['date_scraped'])
        
        # Extract numeric values from effektiver_jahreszins
        def extract_rate(rate_str):
            if pd.isna(rate_str) or rate_str == '':
                return None
            try:
                # Remove common suffixes and extract number
                rate_str = str(rate_str).replace('%', '').replace('p.a.', '').strip()
                # Handle ranges (take first value)
                if '-' in rate_str:
                    rate_str = rate_str.split('-')[0].strip()
                return float(rate_str)
            except:
                return None
        
        df['rate_numeric'] = df['effektiver_jahreszins'].apply(extract_rate)
        df = df.dropna(subset=['rate_numeric'])
        
        if df.empty:
            print("✗ No valid numeric rates found")
            return {}
        
        # Group by bank and date
        chart_data = {}
        banks = df['bank_name'].unique()
        
        for bank in banks:
            bank_data = df[df['bank_name'] == bank].copy()
            bank_data = bank_data.sort_values('date_scraped')
            
            # Group by date and take the average rate for that day
            daily_rates = bank_data.groupby(bank_data['date_scraped'].dt.date)['rate_numeric'].mean()
            
            chart_data[bank] = {
                'dates': daily_rates.index.tolist(),
                'rates': daily_rates.values.tolist()
            }
        
        print(f"✓ Prepared chart data for {len(chart_data)} banks")
        return chart_data
    
    def create_interest_rate_chart(self, chart_data: Dict, output_file: str = 'database_interest_rate_chart.png'):
        """Create a line chart from the database data"""
        if not chart_data:
            print("✗ No data available for charting")
            return False
        
        plt.figure(figsize=(14, 8))
        
        # Define colors for banks
        colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f']
        
        for i, (bank, data) in enumerate(chart_data.items()):
            if not data['dates'] or not data['rates']:
                continue
                
            # Convert dates to datetime objects
            dates = [datetime.combine(d, datetime.min.time()) for d in data['dates']]
            
            plt.plot(dates, data['rates'], 
                    marker='o', 
                    linewidth=2.5, 
                    markersize=6,
                    label=bank, 
                    color=colors[i % len(colors)])
        
        # Customize the plot
        plt.title('Effective Interest Rate Development - Austrian Banks\n(From Database)', 
                  fontsize=16, fontweight='bold', pad=20)
        plt.xlabel('Date', fontsize=12, fontweight='bold')
        plt.ylabel('Effective Interest Rate (%)', fontsize=12, fontweight='bold')
        
        # Format x-axis
        plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%d.%m.%Y'))
        plt.xticks(rotation=45)
        
        # Add grid
        plt.grid(True, alpha=0.3, linestyle='--')
        
        # Add legend
        plt.legend(loc='best', frameon=True, shadow=True)
        
        # Adjust layout
        plt.tight_layout()
        
        # Save chart
        plt.savefig(output_file, dpi=300, bbox_inches='tight', 
                   facecolor='white', edgecolor='none')
        
        print(f"✓ Chart saved as: {output_file}")
        plt.show()
        
        return True
    
    def create_summary_statistics(self, chart_data: Dict):
        """Create summary statistics from the data"""
        print("\n" + "="*60)
        print("SUMMARY STATISTICS")
        print("="*60)
        
        for bank, data in chart_data.items():
            if not data['rates']:
                continue
                
            rates = data['rates']
            print(f"\n🏦 {bank}:")
            print(f"   Data Points: {len(rates)}")
            print(f"   Date Range: {data['dates'][0]} to {data['dates'][-1]}")
            print(f"   Current Rate: {rates[-1]:.2f}%")
            print(f"   Average Rate: {np.mean(rates):.2f}%")
            print(f"   Min Rate: {min(rates):.2f}%")
            print(f"   Max Rate: {max(rates):.2f}%")
            if len(rates) > 1:
                print(f"   Rate Change: {rates[-1] - rates[0]:+.2f}%")
    
    def generate_charts(self):
        """Main method to generate charts from database"""
        print("🚀 Starting database chart generation...")
        
        # Analyze database
        if not self.analyze_database():
            return False
        
        # Extract chart data
        chart_data = self.extract_chart_data()
        if not chart_data:
            return False
        
        # Create chart
        if self.create_interest_rate_chart(chart_data):
            # Show summary statistics
            self.create_summary_statistics(chart_data)
            return True
        
        return False

def main():
    """Main function to test database chart generation"""
    print("🔍 Database Chart Generator Test")
    print("="*50)
    
    # Check which database files exist
    db_files = ['austrian_banks.db', 'austrian_banks_housing_loan.db']
    available_dbs = [db for db in db_files if os.path.exists(db)]
    
    if not available_dbs:
        print("✗ No database files found!")
        return
    
    print(f"📁 Found database files: {', '.join(available_dbs)}")
    
    # Test with the first available database
    db_path = available_dbs[0]
    print(f"\n🎯 Testing with: {db_path}")
    
    # Create chart generator
    generator = DatabaseChartGenerator(db_path)
    
    # Generate charts
    success = generator.generate_charts()
    
    if success:
        print("\n✅ Chart generation completed successfully!")
    else:
        print("\n❌ Chart generation failed!")
    
    # Close database connection
    generator.analyzer.close()

if __name__ == "__main__":
    main()
