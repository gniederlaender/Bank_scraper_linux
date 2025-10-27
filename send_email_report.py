#!/usr/bin/env python3
"""
Email Report Sender
Sends HTML comparison reports via email
"""

import os
import sys
import smtplib
import logging
import argparse
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import glob

# Try to load dotenv if available (optional for test mode)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not available, will use environment variables

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('email_report.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class EmailReportSender:
    """Handles sending email reports with HTML content and attachments"""
    
    def __init__(self, report_type='wohnkredit'):
        """
        Initialize email sender
        
        Args:
            report_type: Type of report ('wohnkredit' or 'konsumkredit')
        """
        self.report_type = report_type
        self.email_host = os.getenv('EMAIL_HOST')
        self.email_port = int(os.getenv('EMAIL_PORT', '587'))
        self.email_user = os.getenv('EMAIL_USER')
        self.email_password = os.getenv('EMAIL_PASSWORD')
        
        # Select recipients based on report type
        if report_type == 'wohnkredit':
            recipients_str = os.getenv('EMAIL_RECIPIENTS_WOHNKREDIT', '')
        else:
            recipients_str = os.getenv('EMAIL_RECIPIENTS_KONSUMKREDIT', '')
        
        self.email_recipients = [r.strip() for r in recipients_str.split(',') if r.strip()]
        
        # Validate configuration
        self._validate_config()
    
    def _validate_config(self):
        """Validate email configuration"""
        if not self.email_host:
            raise ValueError("EMAIL_HOST not configured in .env file")
        if not self.email_user:
            raise ValueError("EMAIL_USER not configured in .env file")
        if not self.email_password:
            raise ValueError("EMAIL_PASSWORD not configured in .env file")
        if not self.email_recipients:
            env_var = 'EMAIL_RECIPIENTS_WOHNKREDIT' if self.report_type == 'wohnkredit' else 'EMAIL_RECIPIENTS_KONSUMKREDIT'
            raise ValueError(f"{env_var} not configured in .env file")
        
        logger.info(f"Email configuration validated for {self.report_type}")
        logger.info(f"Recipients: {', '.join(self.email_recipients)}")
    
    def send_report(self, html_file_path, subject=None, include_screenshots=False):
        """
        Send email report with HTML content
        
        Args:
            html_file_path: Path to HTML file to send
            subject: Email subject (optional, will use default based on report type)
            include_screenshots: Whether to include screenshot attachments
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Read HTML content
            if not os.path.exists(html_file_path):
                logger.error(f"HTML file not found: {html_file_path}")
                return False
            
            with open(html_file_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
            
            # Set default subject if not provided
            if subject is None:
                if self.report_type == 'wohnkredit':
                    subject = "Aktuelle Konditionen Wohnkredite in Österreich - Durchblicker.at"
                else:
                    subject = "Aktuelle Konditionen Konsumkredite in Österreich"
            
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.email_user
            msg['To'] = ', '.join(self.email_recipients)
            
            # Attach HTML content
            html_part = MIMEText(html_content, 'html')
            msg.attach(html_part)
            
            # Add screenshot attachments if requested
            if include_screenshots:
                self._add_screenshot_attachments(msg)
            
            # Send email
            with smtplib.SMTP(self.email_host, self.email_port) as server:
                server.starttls()
                server.login(self.email_user, self.email_password)
                server.send_message(msg)
            
            logger.info(f"Email sent successfully to {', '.join(self.email_recipients)}")
            logger.info(f"   Subject: {subject}")
            logger.info(f"   HTML file: {html_file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending email: {e}")
            return False
    
    def _add_screenshot_attachments(self, msg):
        """Add screenshot attachments to email"""
        screenshots_dir = './screenshots'
        
        if not os.path.exists(screenshots_dir):
            logger.warning(f"Screenshots directory not found: {screenshots_dir}")
            return
        
        screenshot_files = glob.glob(os.path.join(screenshots_dir, '*'))
        
        if not screenshot_files:
            logger.info("No screenshots found to attach")
            return
        
        attached_count = 0
        for file_path in screenshot_files:
            if os.path.isfile(file_path):
                try:
                    filename = os.path.basename(file_path)
                    
                    with open(file_path, 'rb') as attachment:
                        part = MIMEBase('application', 'octet-stream')
                        part.set_payload(attachment.read())
                    
                    encoders.encode_base64(part)
                    part.add_header(
                        'Content-Disposition',
                        f'attachment; filename={filename}'
                    )
                    
                    msg.attach(part)
                    logger.info(f"   Attached screenshot: {filename}")
                    attached_count += 1
                    
                except Exception as e:
                    logger.error(f"   Error attaching {file_path}: {e}")
        
        logger.info(f"Attached {attached_count} screenshot(s)")


def main():
    """Main function with command line argument parsing"""
    parser = argparse.ArgumentParser(
        description='Send bank comparison HTML reports via email',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Send housing loan report (Durchblicker)
  %(prog)s bank_comparison_housing_loan_durchblicker.html --type wohnkredit

  # Send consumer loan report
  %(prog)s bank_comparison.html --type konsumkredit

  # Send with custom subject
  %(prog)s report.html --type wohnkredit --subject "Custom Subject"

  # Send with screenshots attached
  %(prog)s report.html --type wohnkredit --screenshots
        """
    )
    
    parser.add_argument(
        'html_file',
        help='Path to HTML file to send'
    )
    
    parser.add_argument(
        '--type',
        choices=['wohnkredit', 'konsumkredit'],
        default='wohnkredit',
        help='Type of report (default: wohnkredit)'
    )
    
    parser.add_argument(
        '--subject',
        help='Email subject (optional, uses default based on type)'
    )
    
    parser.add_argument(
        '--screenshots',
        action='store_true',
        help='Include screenshot attachments from ./screenshots directory'
    )
    
    parser.add_argument(
        '--test',
        action='store_true',
        help='Test mode: Validate configuration without sending email'
    )
    
    args = parser.parse_args()
    
    # Display header
    logger.info("=" * 60)
    logger.info("Email Report Sender")
    logger.info("=" * 60)
    
    try:
        # Check if HTML file exists
        if not os.path.exists(args.html_file):
            logger.error(f"HTML file not found: {args.html_file}")
            sys.exit(1)
        
        # Test mode: Just validate configuration without sending
        if args.test:
            logger.info("TEST MODE: Validating configuration (no email will be sent)...")
            logger.info("=" * 60)
            
            # Check email configuration
            logger.info("Checking email configuration...")
            try:
                sender = EmailReportSender(report_type=args.type)
                
                # Read and validate HTML content
                logger.info(f"\nReading HTML file: {args.html_file}")
                with open(args.html_file, 'r', encoding='utf-8') as f:
                    html_content = f.read()
                    logger.info(f"HTML file is valid ({len(html_content)} characters)")
                
                logger.info("\n" + "=" * 60)
                logger.info("[TEST MODE] Configuration is valid!")
                logger.info("=" * 60)
                logger.info(f"EMAIL_HOST: {sender.email_host}")
                logger.info(f"EMAIL_PORT: {sender.email_port}")
                logger.info(f"EMAIL_USER: {sender.email_user}")
                logger.info(f"Recipients: {', '.join(sender.email_recipients)}")
                logger.info(f"HTML file: {args.html_file} ({len(html_content)} chars)")
                logger.info("=" * 60)
                logger.info("To send email, run without --test flag")
                sys.exit(0)
            except ValueError as e:
                logger.error("\n[TEST MODE] Configuration incomplete:")
                logger.error(f"  {e}")
                logger.error("\nTo use test mode, you need a .env file or set environment variables:")
                logger.error("  EMAIL_HOST, EMAIL_PORT, EMAIL_USER, EMAIL_PASSWORD, EMAIL_RECIPIENTS")
                logger.info("\nHowever, you can still use the script without .env file if you set these as environment variables.")
                sys.exit(1)
        
        # Create sender and send email
        sender = EmailReportSender(report_type=args.type)
        success = sender.send_report(
            html_file_path=args.html_file,
            subject=args.subject,
            include_screenshots=args.screenshots
        )
        
        if success:
            logger.info("=" * 60)
            logger.info("Email sent successfully!")
            logger.info("=" * 60)
            sys.exit(0)
        else:
            logger.error("=" * 60)
            logger.error("Failed to send email")
            logger.error("=" * 60)
            sys.exit(1)
    
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        logger.error("Please check your .env file")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
