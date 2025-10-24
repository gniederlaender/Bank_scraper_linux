#!/bin/bash
#
# Complete workflow for Durchblicker.at Housing Loan Scraper
# This script runs the scraper, saves to database, and generates the HTML report
#

echo "============================================================"
echo "Durchblicker.at Housing Loan Scraper - Full Workflow"
echo "============================================================"
echo ""

cd /opt/Bankcomparison

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

# Step 4: Copy HTML to web server
echo "Step 4: Copying HTML to web server..."
cp bank_comparison_housing_loan_durchblicker.html /var/www/smartprototypes.net/public_html/Bank_market_overview/
COPY_EXIT=$?

if [ $COPY_EXIT -ne 0 ]; then
    echo "⚠️  Failed to copy HTML to web server (exit code: $COPY_EXIT)"
    echo "   Check permissions for: /var/www/smartprototypes.net/public_html/Bank_market_overview/"
else
    echo "✅ HTML copied to web server!"
fi

echo ""

# Step 5: Send email report (using email-friendly version with static PNG)
echo "Step 5: Sending email report..."
python3 send_email_report.py bank_comparison_housing_loan_durchblicker_email.html --type wohnkredit
EMAIL_EXIT=$?

if [ $EMAIL_EXIT -ne 0 ]; then
    echo "⚠️  Failed to send email report (exit code: $EMAIL_EXIT)"
    echo "   Check email configuration in .env file"
else
    echo "✅ Email report sent successfully!"
fi

echo ""
echo "============================================================"
echo "✅ Complete workflow finished successfully!"
echo "============================================================"
echo ""
echo "Output files:"
echo "  📄 HTML: /opt/Bankcomparison/bank_comparison_housing_loan_durchblicker.html"
echo "  🌐 Web:  /var/www/smartprototypes.net/public_html/Bank_market_overview/bank_comparison_housing_loan_durchblicker.html"
echo "  🗄️  Database: /opt/Bankcomparison/austrian_banks_housing_loan.db"
echo "  📧 Email: Sent to configured recipients"
echo ""
echo "View report locally: file:///opt/Bankcomparison/bank_comparison_housing_loan_durchblicker.html"
echo "View report online:  http://smartprototypes.net/Bank_market_overview/bank_comparison_housing_loan_durchblicker.html"
echo ""

