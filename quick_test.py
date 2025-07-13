#!/usr/bin/env python3
"""
Quick test script for the refactored Austrian bank scraper
Usage: python quick_test.py [bank_name]
"""

import sys
import os
from austrian_bankscraper_refactored import ScraperOrchestrator

def main():
    """Main function"""
    print("🧪 Quick Test - Refactored Austrian Bank Scraper")
    print("=" * 50)
    
    # Parse command line arguments
    if len(sys.argv) > 1:
        bank_name = sys.argv[1].lower()
        available_banks = ['raiffeisen', 'bawag', 'bank99', 'erste']
        
        if bank_name in available_banks:
            enabled_banks = [bank_name]
            print(f"Testing single bank: {bank_name}")
        else:
            print(f"❌ Unknown bank: {bank_name}")
            print(f"Available banks: {', '.join(available_banks)}")
            return
    else:
        enabled_banks = ['raiffeisen', 'bawag', 'bank99', 'erste']
        print("Testing all banks")
    
    print(f"Enabled banks: {enabled_banks}")
    print()
    
    # Run the scraper
    try:
        orchestrator = ScraperOrchestrator(enabled_banks=enabled_banks)
        orchestrator.run()
        print("\n✅ Test completed successfully!")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()