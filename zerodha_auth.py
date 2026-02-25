"""
Zerodha Kite Connect authentication script.

Flow:
1. Reads API key and secret from environment variables (or .env file).
2. Prints the Zerodha login URL.
3. Accepts the request_token from the user (pasted after logging in).
4. Exchanges the request_token for an access_token.
5. Saves the access_token to 'access_token.txt'.
"""

import os
import sys

from dotenv import load_dotenv
from kiteconnect import KiteConnect

TOKEN_FILE = "access_token.txt"


def load_credentials():
    """Load API key and secret from environment / .env file."""
    load_dotenv()
    api_key = os.getenv("ZERODHA_API_KEY")
    api_secret = os.getenv("ZERODHA_API_SECRET")
    if not api_key or not api_secret:
        print(
            "Error: ZERODHA_API_KEY and ZERODHA_API_SECRET must be set "
            "in the environment or in a .env file."
        )
        sys.exit(1)
    return api_key, api_secret


def get_request_token(kite):
    """Print the login URL and prompt the user to paste the request_token."""
    login_url = kite.login_url()
    print("\nOpen the following URL in your browser to log in to Zerodha:")
    print(f"  {login_url}\n")
    print(
        "After logging in you will be redirected to your redirect URL.\n"
        "Copy the value of the 'request_token' query parameter from that URL."
    )
    request_token = input("Paste the request_token here: ").strip()
    if not request_token:
        print("Error: request_token cannot be empty.")
        sys.exit(1)
    return request_token


def generate_session(kite, api_secret, request_token):
    """Exchange the request_token for an access_token."""
    data = kite.generate_session(request_token, api_secret=api_secret)
    return data["access_token"]


def save_token(access_token):
    """Persist the access_token to TOKEN_FILE."""
    with open(TOKEN_FILE, "w") as fh:
        fh.write(access_token)
    print(f"\nAccess token saved to '{TOKEN_FILE}'.")


def main():
    api_key, api_secret = load_credentials()
    kite = KiteConnect(api_key=api_key)

    request_token = get_request_token(kite)
    access_token = generate_session(kite, api_secret, request_token)

    kite.set_access_token(access_token)
    print(f"Successfully authenticated. Access token: {access_token}")

    save_token(access_token)


if __name__ == "__main__":
    main()
