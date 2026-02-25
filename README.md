# AllIN
All in using Zerodha APIs

## Zerodha API Authentication

`zerodha_auth.py` authenticates with the [Zerodha Kite Connect API](https://kite.trade/docs/connect/v3/) and saves the access token to `access_token.txt`.

### Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and fill in your credentials:
   ```bash
   cp .env.example .env
   ```
   Edit `.env`:
   ```
   ZERODHA_API_KEY=your_api_key_here
   ZERODHA_API_SECRET=your_api_secret_here
   ```

### Usage

```bash
python zerodha_auth.py
```

The script will:
1. Print a Zerodha login URL — open it in your browser.
2. After logging in, copy the `request_token` from the redirect URL.
3. Paste it into the terminal when prompted.
4. The access token is saved to `access_token.txt` for use by other scripts.

### Credentials

| Variable | Description |
|---|---|
| `ZERODHA_API_KEY` | API key from the [Kite Connect developer console](https://developers.kite.trade/) |
| `ZERODHA_API_SECRET` | API secret from the same console |
