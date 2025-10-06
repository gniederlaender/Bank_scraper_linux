#!/usr/bin/env python3
"""
Database Chart Generator - Using View
Extracts data from austrian_banks.db using the chart-ready view and creates interest rate development charts.
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

class DatabaseAnalyzerView:
    """Analyzes the SQLite database using the chart-ready view"""
    
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
    
    def get_view_info(self) -> Dict:
        """Get information about the chart-ready view"""
        if not self.conn:
            return {}
        
        cursor = self.conn.cursor()
        
        # Check if view exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='view' AND name='interest_rates_chart_ready'")
        view_exists = cursor.fetchone()
        
        if not view_exists:
            print("✗ View 'interest_rates_chart_ready' does not exist!")
            return {}
        
        # Get row count
        cursor.execute("SELECT COUNT(*) FROM interest_rates_chart_ready")
        row_count = cursor.fetchone()[0]
        
        # Get sample data
        cursor.execute("SELECT * FROM interest_rates_chart_ready LIMIT 3")
        sample_data = cursor.fetchall()
        
        # Get column names
        cursor.execute("PRAGMA table_info(interest_rates_chart_ready)")
        columns = [col[1] for col in cursor.fetchall()]
        
        return {
            'row_count': row_count,
            'sample_data': sample_data,
            'columns': columns
        }
    
    def get_interest_rate_data(self) -> pd.DataFrame:
        """Extract interest rate data from the chart-ready view"""
        if not self.conn:
            return pd.DataFrame()
        
        query = """
        SELECT 
            bank_name,
            product_name,
            effektiver_jahreszins_numeric as effektiver_jahreszins,
            date_scraped,
            nettokreditbetrag_numeric as nettokreditbetrag,
            vertragslaufzeit_numeric as vertragslaufzeit,
            source_url,
            rate_numeric as rate
        FROM interest_rates_chart_ready 
        WHERE effektiver_jahreszins_numeric IS NOT NULL 
        ORDER BY date_scraped, bank_name
        """
        
        try:
            df = pd.read_sql_query(query, self.conn)
            print(f"✓ Extracted {len(df)} interest rate records from view")
            return df
        except Exception as e:
            print(f"✗ Error extracting data from view: {e}")
            return pd.DataFrame()
    
    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()

class DatabaseChartGeneratorView:
    """Generates charts from database data using the view"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.analyzer = DatabaseAnalyzerView(db_path)
        
    def analyze_database(self):
        """Analyze the database structure and view content"""
        print("="*60)
        print("DATABASE ANALYSIS (Using View)")
        print("="*60)
        
        if not self.analyzer.connect():
            return False
        
        # Get view information
        view_info = self.analyzer.get_view_info()
        
        if not view_info:
            return False
        
        print(f"\n📊 Chart-Ready View: interest_rates_chart_ready")
        print(f"   Rows: {view_info['row_count']}")
        print(f"   Columns: {len(view_info['columns'])}")
        print(f"   Numeric columns: {[col for col in view_info['columns'] if col.endswith('_numeric')]}")
        
        if view_info['sample_data']:
            print("   Sample cleaned data:")
            for i, row in enumerate(view_info['sample_data'][:2]):  # Show first 2 rows
                # Get column indices for bank_name, rate_numeric, effektiver_jahreszins_numeric
                bank_idx = view_info['columns'].index('bank_name')
                rate_idx = view_info['columns'].index('rate_numeric')
                eff_zins_idx = view_info['columns'].index('effektiver_jahreszins_numeric')
                print(f"     Row {i+1}: Bank={row[bank_idx]}, Rate={row[rate_idx]}, Eff.Zins={row[eff_zins_idx]}")
        
        return True
    
    def extract_chart_data(self) -> Dict:
        """Extract data suitable for charting from the view"""
        if not self.analyzer.connect():
            return {}
        
        df = self.analyzer.get_interest_rate_data()
        if df.empty:
            print("✗ No data found for charting")
            return {}
        
        # Clean and process the data
        df['date_scraped'] = pd.to_datetime(df['date_scraped'])
        
        # Data is already cleaned from the view, just ensure it's numeric
        df['rate_numeric'] = pd.to_numeric(df['effektiver_jahreszins'], errors='coerce')
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
        
        print(f"✓ Prepared chart data for {len(chart_data)} banks using view")
        return chart_data
    
    def create_interest_rate_chart(self, chart_data: Dict, output_file: str = 'database_interest_rate_chart_view.png'):
        """Create a line chart from the database data using the view"""
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
        plt.title('Effective Interest Rate Development - Austrian Banks\n(From Database View)', 
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
        print("SUMMARY STATISTICS (From View)")
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
        """Main method to generate charts from database using view"""
        print("🚀 Starting database chart generation using view...")
        
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
    """Main function to test database chart generation using view"""
    print("🔍 Database Chart Generator Test (Using View)")
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
    generator = DatabaseChartGeneratorView(db_path)
    
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
