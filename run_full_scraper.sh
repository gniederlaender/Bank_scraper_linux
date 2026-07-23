#!/bin/bash
#
# Complete workflow for Durchblicker.at Loan Scrapers
# This script runs scrapers for both housing loans (Wohnkredit) and consumer loans (Konsumkredit)
#
# Flags:
#   --noscraping  Skip the housing loan and consumer loan scraping steps
#                 (view/report generation still runs against existing DB data)
#   --noemail     Skip sending the housing loan and consumer loan email reports
#

NOSCRAPING=false
NOEMAIL=false
for arg in "$@"; do
    case "$arg" in
        --noscraping)
            NOSCRAPING=true
            ;;
        --noemail)
            NOEMAIL=true
            ;;
        *)
            echo "⚠️  Unknown argument: $arg"
            ;;
    esac
done

echo "============================================================"
echo "Austrian Bank Scraper - Full Workflow"
echo "Housing Loans + Consumer Loans"
if [ "$NOSCRAPING" = true ]; then
    echo "Flag: --noscraping (scraping steps will be skipped)"
fi
if [ "$NOEMAIL" = true ]; then
    echo "Flag: --noemail (email reports will not be sent)"
fi
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
if [ "$NOSCRAPING" = true ]; then
    echo "Step 1: Skipping Durchblicker.at housing loan scraper (--noscraping)"
    echo ""
else
    echo "Step 1: Running Durchblicker.at housing loan scraper..."
    python3 test_durchblicker.py
    SCRAPER_EXIT=$?

    if [ $SCRAPER_EXIT -ne 0 ]; then
        echo "❌ Housing loan scraper failed with exit code: $SCRAPER_EXIT"
        exit 1
    fi

    echo "✅ Housing loan scraper completed successfully!"
    echo ""
fi

# Step 2: Create/update the housing loan database view
echo "Step 2: Creating/updating housing loan database view..."
python3 create_housing_loan_view.py
VIEW_EXIT=$?

if [ $VIEW_EXIT -ne 0 ]; then
    echo "⚠️  Housing loan view creation failed, but continuing..."
fi

echo ""

# Step 2b: Update SWAP/Euribor rates from ECB and Sparkasse APIs
if [ "$NOSCRAPING" = true ]; then
    echo "Step 2b: Skipping SWAP/Euribor rates update (--noscraping)"
    echo ""
else
    echo "Step 2b: Updating SWAP/Euribor rates..."
    # Calculate date range: 12 months back to current month
    START_DATE=$(date -d "12 months ago" +%Y-%m)
    END_DATE=$(date +%Y-%m)
    python3 swap_data_fetcher.py --start "$START_DATE" --end "$END_DATE" --output swap_data.js
    SWAP_EXIT=$?

    if [ $SWAP_EXIT -ne 0 ]; then
        echo "⚠️  SWAP/Euribor rates update failed (exit code: $SWAP_EXIT)"
        echo "   Continuing with cached rates..."
    else
        echo "✅ SWAP/Euribor rates updated successfully!"
    fi

    echo ""
fi

# Step 3: Run OeNB Nachfrage scraper to capture dashboard charts
if [ "$NOSCRAPING" = true ]; then
    echo "Step 3: Skipping OeNB Nachfrage scraper (--noscraping)"
    echo ""
else
    echo "Step 3: Running OeNB Nachfrage scraper..."
    python3 oenb_nachfrage_scraper.py
    OENB_EXIT=$?

    if [ $OENB_EXIT -ne 0 ]; then
        echo "⚠️  OeNB scraper failed with exit code: $OENB_EXIT"
        echo "   Continuing without OeNB charts..."
    else
        echo "✅ OeNB scraper completed successfully!"
    fi

    echo ""
fi

# Step 4: Generate housing loan HTML report with chart
echo "Step 4: Generating housing loan HTML report and chart..."
python3 generate_housing_loan_html.py
HTML_EXIT=$?

if [ $HTML_EXIT -ne 0 ]; then
    echo "❌ Housing loan HTML generation failed with exit code: $HTML_EXIT"
    exit 1
fi

echo "✅ Housing loan HTML generated successfully!"
echo ""

# Step 5: Copy housing loan HTML to web server
echo "Step 5: Copying housing loan HTML to web server..."
cp bank_comparison_housing_loan_durchblicker.html /var/www/smartprototypes.net/public_html/Bank_market_overview/
COPY_EXIT=$?

if [ $COPY_EXIT -ne 0 ]; then
    echo "⚠️  Failed to copy housing loan HTML to web server (exit code: $COPY_EXIT)"
    echo "   Check permissions for: /var/www/smartprototypes.net/public_html/Bank_market_overview/"
else
    echo "✅ Housing loan HTML copied to web server!"
fi

# Step 5a: Copy screenshots directory to web server
echo "Step 5a: Copying screenshots directory to web server..."
if [ -d "screenshots" ]; then
    # Create screenshots directory on web server if it doesn't exist
    mkdir -p /var/www/smartprototypes.net/public_html/Bank_market_overview/screenshots
    SCREENSHOTS_COPY_EXIT=$?
    
    if [ $SCREENSHOTS_COPY_EXIT -ne 0 ]; then
        echo "⚠️  Failed to create screenshots directory on web server (exit code: $SCREENSHOTS_COPY_EXIT)"
    else
        # Copy all screenshot files
        cp screenshots/*.png /var/www/smartprototypes.net/public_html/Bank_market_overview/screenshots/ 2>/dev/null
        SCREENSHOTS_COPY_EXIT=$?
        
        if [ $SCREENSHOTS_COPY_EXIT -ne 0 ]; then
            echo "⚠️  Failed to copy screenshots to web server (exit code: $SCREENSHOTS_COPY_EXIT)"
            echo "   This is OK if no screenshots exist yet"
        else
            SCREENSHOT_COUNT=$(ls -1 screenshots/*.png 2>/dev/null | wc -l)
            echo "✅ Screenshots directory copied to web server! ($SCREENSHOT_COUNT files)"
        fi
    fi
else
    echo "⚠️  Screenshots directory not found - skipping screenshot copy"
fi

echo ""
# Step 5b: Generate housing loan HTML with AI LLM commentary
echo "Step 5b: Generating LLM housing loan commentary (beta)..."
# Remove any stale commented file from a previous run first, so a failed
# commentary step can never cause an outdated report to be emailed.
rm -f bank_comparison_housing_loan_durchblicker_email_commented.html
python3 llm_housing_commentary.py --input bank_comparison_housing_loan_durchblicker_email.html --output bank_comparison_housing_loan_durchblicker_email_commented.html
LLM_COMMENT_EXIT=$?

if [ $LLM_COMMENT_EXIT -ne 0 ]; then
    echo "⚠️  Failed to generate LLM housing loan commentary (exit code: $LLM_COMMENT_EXIT)"
    echo "   Falling back to email report WITHOUT commentary (fresh data)"
    HOUSING_EMAIL_FILE=bank_comparison_housing_loan_durchblicker_email.html
else
    echo "✅ LLM housing loan commentary generated!"
    HOUSING_EMAIL_FILE=bank_comparison_housing_loan_durchblicker_email_commented.html
fi

echo ""

# Step 6: Send housing loan email report
if [ "$NOEMAIL" = true ]; then
    echo "Step 6: Skipping housing loan email report (--noemail)"
else
    echo "Step 6: Sending housing loan email report ($HOUSING_EMAIL_FILE)..."
    python3 send_email_report.py "$HOUSING_EMAIL_FILE" --type wohnkredit
    EMAIL_EXIT=$?

    if [ $EMAIL_EXIT -ne 0 ]; then
        echo "⚠️  Failed to send housing loan email report (exit code: $EMAIL_EXIT)"
        echo "   Check email configuration in .env file"
    else
        echo "✅ Housing loan email report sent successfully!"
    fi
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
if [ "$NOSCRAPING" = true ]; then
    echo "Step 1: Skipping consumer loan scraper (--noscraping)"
    echo ""
else
    echo "Step 1: Running consumer loan scraper..."
    python3 austrian_bankscraper_linux.py
    CONSUMER_SCRAPER_EXIT=$?

    if [ $CONSUMER_SCRAPER_EXIT -ne 0 ]; then
        echo "❌ Consumer loan scraper failed with exit code: $CONSUMER_SCRAPER_EXIT"
        exit 1
    fi

    echo "✅ Consumer loan scraper completed successfully!"
    echo ""
fi

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
# Remove any stale commented file from a previous run first, so a failed
# commentary step can never cause an outdated report to be emailed.
rm -f bank_comparison_consumer_loan_email_commented.html
python3 llm_consumer_commentary.py --input bank_comparison_consumer_loan_email.html --output bank_comparison_consumer_loan_email_commented.html
CONSUMER_LLM_COMMENTARY_EXIT=$?

if [ $CONSUMER_LLM_COMMENTARY_EXIT -ne 0 ]; then
    echo "⚠️  Failed to generate LLM commentary for consumer loan email (exit code: $CONSUMER_LLM_COMMENTARY_EXIT)"
    echo "   Falling back to email report WITHOUT commentary (fresh data)"
    CONSUMER_EMAIL_FILE=bank_comparison_consumer_loan_email.html
else
    echo "✅ LLM commentary for consumer loan email generated!"
    CONSUMER_EMAIL_FILE=bank_comparison_consumer_loan_email_commented.html
fi

echo ""

# Step 5: Send consumer loan email report
if [ "$NOEMAIL" = true ]; then
    echo "Step 5: Skipping consumer loan email report (--noemail)"
else
    echo "Step 5: Sending consumer loan email report ($CONSUMER_EMAIL_FILE)..."
    python3 send_email_report.py "$CONSUMER_EMAIL_FILE" --type konsumkredit
    CONSUMER_EMAIL_EXIT=$?

    if [ $CONSUMER_EMAIL_EXIT -ne 0 ]; then
        echo "⚠️  Failed to send consumer loan email report (exit code: $CONSUMER_EMAIL_EXIT)"
        echo "   Check email configuration in .env file"
    else
        echo "✅ Consumer loan email report sent successfully!"
    fi
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
echo "  📈 SWAP Rates: /opt/Bankcomparison/swap_data.js (auto-updated from ECB/Sparkasse)"
echo ""
echo "💳 Consumer Loan (Konsumkredit) Output Files:"
echo "  📄 HTML: /opt/Bankcomparison/bank_comparison_consumer_loan.html"
echo "  🌐 Web:  http://smartprototypes.net/Bank_market_overview/bank_comparison_consumer_loan.html"
echo "  🗄️  Database: /opt/Bankcomparison/austrian_banks.db"
echo ""
if [ "$NOEMAIL" = true ]; then
    echo "📧 Emails: Skipped (--noemail)"
else
    echo "📧 Emails: Sent to configured recipients"
fi
echo ""

