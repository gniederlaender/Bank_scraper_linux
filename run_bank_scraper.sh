#!/bin/bash

# Set the working directory
cd /opt/Bankcomparison

# Activate virtual environment
source venv/bin/activate

# Run the Python script
python austrian_bankscraper_linux.py

# Deactivate virtual environment
deactivate
