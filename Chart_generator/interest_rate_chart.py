#!/usr/bin/env python3
"""
Interest Rate Development Chart
Creates a line chart showing the development of effective interest rates
for 4 Austrian banks over time using the test dataset.
"""

import json
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
import numpy as np

def load_test_data(json_file):
    """Load the test dataset from JSON file."""
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data['test_dataset']

def parse_dates(date_strings):
    """Convert date strings to datetime objects."""
    return [datetime.strptime(date, '%d.%m.%Y') for date in date_strings]

def create_interest_rate_chart(data):
    """Create a line chart showing interest rate development over time."""
    
    # Extract data
    banks = data['banks']
    dates = parse_dates(data['dates'])
    rate_data = data['data']
    
    # Prepare data for plotting
    bank_rates = {bank: [] for bank in banks}
    
    for date_entry in rate_data:
        for bank in banks:
            bank_rates[bank].append(date_entry['rates'][bank])
    
    # Create the plot
    plt.figure(figsize=(12, 8))
    
    # Define colors for each bank
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728']
    
    # Plot lines for each bank
    for i, bank in enumerate(banks):
        plt.plot(dates, bank_rates[bank], 
                marker='o', 
                linewidth=2.5, 
                markersize=8,
                label=bank, 
                color=colors[i])
    
    # Customize the plot
    plt.title('Effective Interest Rate Development - Austrian Banks\nJanuary 2025', 
              fontsize=16, fontweight='bold', pad=20)
    plt.xlabel('Date', fontsize=12, fontweight='bold')
    plt.ylabel('Effective Interest Rate (%)', fontsize=12, fontweight='bold')
    
    # Format x-axis
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%d.%m.%Y'))
    plt.gca().xaxis.set_major_locator(mdates.DayLocator(interval=7))
    plt.xticks(rotation=45)
    
    # Set y-axis range to show the data better
    all_rates = [rate for bank_rates_list in bank_rates.values() for rate in bank_rates_list]
    y_min = min(all_rates) - 0.05
    y_max = max(all_rates) + 0.05
    plt.ylim(y_min, y_max)
    
    # Add grid
    plt.grid(True, alpha=0.3, linestyle='--')
    
    # Add legend
    plt.legend(loc='upper right', frameon=True, shadow=True)
    
    # Add value annotations on the last point for each bank
    for i, bank in enumerate(banks):
        last_rate = bank_rates[bank][-1]
        plt.annotate(f'{last_rate:.2f}%', 
                    xy=(dates[-1], last_rate),
                    xytext=(10, 0), 
                    textcoords='offset points',
                    fontsize=10,
                    bbox=dict(boxstyle='round,pad=0.3', facecolor=colors[i], alpha=0.7))
    
    # Adjust layout to prevent label cutoff
    plt.tight_layout()
    
    return plt

def main():
    """Main function to create and save the chart."""
    try:
        # Load data
        print("Loading test dataset...")
        data = load_test_data('test_dataset.json')
        
        # Create chart
        print("Creating interest rate development chart...")
        plt = create_interest_rate_chart(data)
        
        # Save chart
        output_file = 'interest_rate_development_chart.png'
        plt.savefig(output_file, dpi=300, bbox_inches='tight', 
                   facecolor='white', edgecolor='none')
        
        print(f"Chart saved as: {output_file}")
        
        # Show chart (optional - comment out if running headless)
        plt.show()
        
        # Print summary statistics
        print("\n" + "="*50)
        print("SUMMARY STATISTICS")
        print("="*50)
        
        for bank in data['banks']:
            rates = []
            for date_entry in data['data']:
                rates.append(date_entry['rates'][bank])
            
            print(f"\n{bank}:")
            print(f"  Start Rate: {rates[0]:.2f}%")
            print(f"  End Rate: {rates[-1]:.2f}%")
            print(f"  Change: {rates[-1] - rates[0]:+.2f}%")
            print(f"  Average: {np.mean(rates):.2f}%")
            print(f"  Min: {min(rates):.2f}%")
            print(f"  Max: {max(rates):.2f}%")
        
    except FileNotFoundError:
        print("Error: test_dataset.json not found. Please make sure the file exists.")
    except Exception as e:
        print(f"Error creating chart: {e}")

if __name__ == "__main__":
    main()
