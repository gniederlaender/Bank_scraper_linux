#!/bin/bash
#
# Complete workflow for Durchblicker.at Housing Loan Scraper
# This script runs the scraper, saves to database, and generates the HTML report
#

echo "============================================================"
echo "Durchblicker.at Housing Loan Scraper - Full Workflow"
echo "============================================================"
echo ""

# Activate virtual environment
source venv/bin/activate

# Step 1: Run the scraper
echo "Step 1: Running scraper..."
python3 test_durchblicker.py
SCRAPER_EXIT=$?

if [ $SCRAPER_EXIT -ne 0 ]; then
    echo "❌ Scraper failed with exit code: $SCRAPER_EXIT"
    exit 1
fi

echo "✅ Scraper completed successfully!"
echo ""

# Step 2: Create/update the database view (safe to run multiple times)
echo "Step 2: Creating/updating database view..."
python3 create_housing_loan_view.py
VIEW_EXIT=$?

if [ $VIEW_EXIT -ne 0 ]; then
    echo "⚠️  View creation failed, but continuing..."
fi

echo ""

# Step 3: Generate HTML report with chart
echo "Step 3: Generating HTML report and chart..."
python3 generate_housing_loan_html.py
HTML_EXIT=$?

if [ $HTML_EXIT -ne 0 ]; then
    echo "❌ HTML generation failed with exit code: $HTML_EXIT"
    exit 1
fi

echo ""
echo "============================================================"
echo "✅ Complete workflow finished successfully!"
echo "============================================================"
echo ""
echo "Output files:"
echo "  📄 HTML: /opt/Bankcomparison/bank_comparison_housing_loan_durchblicker.html"
echo "  📊 Chart: /opt/Bankcomparison/housing_loan_chart.png"
echo "  🗄️  Database: /opt/Bankcomparison/austrian_banks_housing_loan.db"
echo ""
echo "View report: file:///opt/Bankcomparison/bank_comparison_housing_loan_durchblicker.html"
echo ""

