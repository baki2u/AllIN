"""
Zerodha Kite Connect client setup and authentication helper.

Usage:
  1. Set KITE_API_KEY and KITE_API_SECRET in .env or environment variables.
  2. Run this script once to complete the OAuth flow:
       python kite_client.py
  3. Copy the printed ACCESS_TOKEN into your .env file as KITE_ACCESS_TOKEN.
  4. Subsequent calls to get_kite_client() will use the stored token.
"""

import sys
import webbrowser
from kiteconnect import KiteConnect
import config


def get_kite_client() -> KiteConnect:
    """Return an authenticated KiteConnect instance."""
    if not config.API_KEY or config.API_KEY == "your_api_key_here":
        raise ValueError(
            "KITE_API_KEY is not set. "
            "Please configure your credentials in a .env file or environment variables. "
            "See config.py for details."
        )

    kite = KiteConnect(api_key=config.API_KEY)

    if not config.ACCESS_TOKEN:
        raise ValueError(
            "KITE_ACCESS_TOKEN is not set. "
            "Run `python kite_client.py` to complete the OAuth flow and obtain a token."
        )

    kite.set_access_token(config.ACCESS_TOKEN)
    return kite


def generate_access_token() -> str:
    """
    Interactively guide the user through Zerodha OAuth to obtain an access token.
    Opens the login URL in the default browser and prompts for the request token.

    Returns:
        The access token string.
    """
    if not config.API_KEY or config.API_KEY == "your_api_key_here":
        raise ValueError(
            "KITE_API_KEY is not set. Please set it in your .env file first."
        )

    kite = KiteConnect(api_key=config.API_KEY)
    login_url = kite.login_url()

    print(f"\nOpening Zerodha login page in your browser:\n  {login_url}\n")
    print(
        "After logging in, you will be redirected to a URL containing "
        "`request_token=XXXXXXXX`."
    )
    print("Copy that request_token value and paste it below.\n")

    try:
        webbrowser.open(login_url)
    except Exception:
        pass  # Browser open is best-effort

    request_token = input("Enter the request_token from the redirect URL: ").strip()
    if not request_token:
        raise ValueError("No request token provided.")

    data = kite.generate_session(request_token, api_secret=config.API_SECRET)
    access_token = data["access_token"]

    print(f"\nAccess token generated successfully:\n  {access_token}")
    print(
        "\nAdd the following line to your .env file:\n"
        f"  KITE_ACCESS_TOKEN={access_token}\n"
    )
    return access_token


if __name__ == "__main__":
    try:
        token = generate_access_token()
        sys.exit(0)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
