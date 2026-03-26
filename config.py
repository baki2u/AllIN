"""
Configuration for Zerodha Kite Connect API.

Copy this file to .env or set these environment variables before running scripts.
Alternatively, set them directly here for quick testing (not recommended for production).

To get your API credentials:
  1. Log in to https://developers.kite.trade/
  2. Create an app to get API_KEY and API_SECRET
  3. Use kite_client.py to complete the OAuth flow and get ACCESS_TOKEN
"""

import os
from dotenv import load_dotenv

load_dotenv()

# Kite Connect API credentials
API_KEY = os.getenv("KITE_API_KEY", "your_api_key_here")
API_SECRET = os.getenv("KITE_API_SECRET", "your_api_secret_here")
ACCESS_TOKEN = os.getenv("KITE_ACCESS_TOKEN", "")

# Screening parameters
TOP_N = int(os.getenv("TOP_N", "20"))           # Number of top results to show
MIN_PRICE = float(os.getenv("MIN_PRICE", "10")) # Minimum stock price filter (₹)
MIN_VOLUME = int(os.getenv("MIN_VOLUME", "100000"))  # Minimum daily volume filter

# Exchange to screen (NSE or BSE)
EXCHANGE = os.getenv("EXCHANGE", "NSE")

# Historical lookback settings
WEEKLY_LOOKBACK_DAYS = int(os.getenv("WEEKLY_LOOKBACK_DAYS", "7"))
REVERSAL_LOOKBACK_DAYS = int(os.getenv("REVERSAL_LOOKBACK_DAYS", "10"))
REVERSAL_MIN_LOSS_DAYS = int(os.getenv("REVERSAL_MIN_LOSS_DAYS", "3"))

# Strategy thresholds
RSI_OVERSOLD = float(os.getenv("RSI_OVERSOLD", "35"))
RSI_PERIOD = int(os.getenv("RSI_PERIOD", "14"))
VOLUME_SURGE_MULTIPLIER = float(os.getenv("VOLUME_SURGE_MULTIPLIER", "2.0"))
HIGH_52W_PROXIMITY_PCT = float(os.getenv("HIGH_52W_PROXIMITY_PCT", "2.0"))
