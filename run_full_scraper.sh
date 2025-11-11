#!/bin/bash
#
# Complete workflow for Durchblicker.at Loan Scrapers
# This script runs scrapers for both housing loans (Wohnkredit) and consumer loans (Konsumkredit)
#

echo "============================================================"
echo "Austrian Bank Scraper - Full Workflow"
echo "Housing Loans + Consumer Loans"
echo "============================================================"
echo ""

cd /opt/Bankcomparison

# Activate virtual environment
source venv/bin/activate

# ========================================================================
# PART 1: HOUSING LOAN (Wohnkredit) WORKFLOW
# ========================================================================
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🏠 HOUSING LOAN (Wohnkredit) Workflow"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Step 1: Run the housing loan scraper
echo "Step 1: Running Durchblicker.at housing loan scraper..."
python3 test_durchblicker.py
SCRAPER_EXIT=$?

if [ $SCRAPER_EXIT -ne 0 ]; then
    echo "❌ Housing loan scraper failed with exit code: $SCRAPER_EXIT"
    exit 1
fi

echo "✅ Housing loan scraper completed successfully!"
echo ""

# Step 2: Create/update the housing loan database view
echo "Step 2: Creating/updating housing loan database view..."
python3 create_housing_loan_view.py
VIEW_EXIT=$?

if [ $VIEW_EXIT -ne 0 ]; then
    echo "⚠️  Housing loan view creation failed, but continuing..."
fi

echo ""

# Step 3: Generate housing loan HTML report with chart
echo "Step 3: Generating housing loan HTML report and chart..."
python3 generate_housing_loan_html.py
HTML_EXIT=$?

if [ $HTML_EXIT -ne 0 ]; then
    echo "❌ Housing loan HTML generation failed with exit code: $HTML_EXIT"
    exit 1
fi

echo "✅ Housing loan HTML generated successfully!"
echo ""

# Step 4: Copy housing loan HTML to web server
echo "Step 4: Copying housing loan HTML to web server..."
cp bank_comparison_housing_loan_durchblicker.html /var/www/smartprototypes.net/public_html/Bank_market_overview/
COPY_EXIT=$?

if [ $COPY_EXIT -ne 0 ]; then
    echo "⚠️  Failed to copy housing loan HTML to web server (exit code: $COPY_EXIT)"
    echo "   Check permissions for: /var/www/smartprototypes.net/public_html/Bank_market_overview/"
else
    echo "✅ Housing loan HTML copied to web server!"
fi

echo ""
# Step 4b: Generate housing loan HTML with AI LLM commentary
echo "Step 4b: Generating LLM housing loan commentary (beta)..."
python3 llm_housing_commentary.py --input bank_comparison_housing_loan_durchblicker_email.html --output bank_comparison_housing_loan_durchblicker_email_commented.html
LLM_COMMENT_EXIT=$?

if [ $LLM_COMMENT_EXIT -ne 0 ]; then
    echo "⚠️  Failed to generate LLM housing loan commentary (exit code: $LLM_COMMENT_EXIT)"
else
    echo "✅ LLM housing loan commentary generated!"
fi

echo ""

# Step 5: Send housing loan email report
echo "Step 5: Sending housing loan email report..."
python3 send_email_report.py bank_comparison_housing_loan_durchblicker_email_commented.html --type wohnkredit
EMAIL_EXIT=$?

if [ $EMAIL_EXIT -ne 0 ]; then
    echo "⚠️  Failed to send housing loan email report (exit code: $EMAIL_EXIT)"
    echo "   Check email configuration in .env file"
else
    echo "✅ Housing loan email report sent successfully!"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🏠 Housing Loan Workflow Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ========================================================================
# PART 2: CONSUMER LOAN (Konsumkredit) WORKFLOW
# ========================================================================
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "💳 CONSUMER LOAN (Konsumkredit) Workflow"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Step 1: Run the consumer loan scraper
echo "Step 1: Running consumer loan scraper..."
python3 austrian_bankscraper_linux.py
CONSUMER_SCRAPER_EXIT=$?

if [ $CONSUMER_SCRAPER_EXIT -ne 0 ]; then
    echo "❌ Consumer loan scraper failed with exit code: $CONSUMER_SCRAPER_EXIT"
    exit 1
fi

echo "✅ Consumer loan scraper completed successfully!"
echo ""

# Step 2: Create/update the consumer loan database view
echo "Step 2: Creating/updating consumer loan database view..."
python3 create_consumer_loan_view.py
CONSUMER_VIEW_EXIT=$?

if [ $CONSUMER_VIEW_EXIT -ne 0 ]; then
    echo "⚠️  Consumer loan view creation failed, but continuing..."
fi

echo ""

# Step 3: Generate consumer loan HTML report with chart
echo "Step 3: Generating consumer loan HTML report and chart..."
python3 generate_consumer_loan_html.py
CONSUMER_HTML_EXIT=$?

if [ $CONSUMER_HTML_EXIT -ne 0 ]; then
    echo "❌ Consumer loan HTML generation failed with exit code: $CONSUMER_HTML_EXIT"
    exit 1
fi

echo "✅ Consumer loan HTML generated successfully!"
echo ""

# Step 4: Copy consumer loan HTML to web server
echo "Step 4: Copying consumer loan HTML to web server..."
cp bank_comparison_consumer_loan.html /var/www/smartprototypes.net/public_html/Bank_market_overview/
CONSUMER_COPY_EXIT=$?

if [ $CONSUMER_COPY_EXIT -ne 0 ]; then
    echo "⚠️  Failed to copy consumer loan HTML to web server (exit code: $CONSUMER_COPY_EXIT)"
    echo "   Check permissions for: /var/www/smartprototypes.net/public_html/Bank_market_overview/"
else
    echo "✅ Consumer loan HTML copied to web server!"
fi

echo ""
# Step 4b: Generate LLM commentary for consumer loan HTML email
echo "Step 4b: Generating LLM commentary for consumer loan HTML email..."
python3 llm_consumer_commentary.py --input bank_comparison_consumer_loan_email.html --output bank_comparison_consumer_loan_email_commented.html
CONSUMER_LLM_COMMENTARY_EXIT=$?

if [ $CONSUMER_LLM_COMMENTARY_EXIT -ne 0 ]; then
    echo "⚠️  Failed to generate LLM commentary for consumer loan email (exit code: $CONSUMER_LLM_COMMENTARY_EXIT)"
else
    echo "✅ LLM commentary for consumer loan email generated!"
fi

echo ""

# Step 5: Send consumer loan email report
echo "Step 5: Sending consumer loan email report..."
python3 send_email_report.py bank_comparison_consumer_loan_email_commented.html --type konsumkredit
CONSUMER_EMAIL_EXIT=$?

if [ $CONSUMER_EMAIL_EXIT -ne 0 ]; then
    echo "⚠️  Failed to send consumer loan email report (exit code: $CONSUMER_EMAIL_EXIT)"
    echo "   Check email configuration in .env file"
else
    echo "✅ Consumer loan email report sent successfully!"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "💳 Consumer Loan Workflow Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ========================================================================
# SUMMARY
# ========================================================================
echo ""
echo "============================================================"
echo "✅ Complete Workflow Finished Successfully!"
echo "============================================================"
echo ""
echo "📊 Housing Loan (Wohnkredit) Output Files:"
echo "  📄 HTML: /opt/Bankcomparison/bank_comparison_housing_loan_durchblicker.html"
echo "  🌐 Web:  http://smartprototypes.net/Bank_market_overview/bank_comparison_housing_loan_durchblicker.html"
echo "  🗄️  Database: /opt/Bankcomparison/austrian_banks_housing_loan.db"
echo ""
echo "💳 Consumer Loan (Konsumkredit) Output Files:"
echo "  📄 HTML: /opt/Bankcomparison/bank_comparison_consumer_loan.html"
echo "  🌐 Web:  http://smartprototypes.net/Bank_market_overview/bank_comparison_consumer_loan.html"
echo "  🗄️  Database: /opt/Bankcomparison/austrian_banks.db"
echo ""
echo "📧 Emails: Sent to configured recipients"
echo ""

