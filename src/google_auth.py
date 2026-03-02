"""
Google OAuth 2.0 authentication for personal Google accounts.

Run this script once to authorize: python -m src.google_auth
It opens a browser, you log in, and a token.json is saved for reuse.

The token includes a refresh_token so it auto-renews without re-login.
"""

import json
import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
]

TOKEN_PATH = os.environ.get("GOOGLE_TOKEN_PATH", "token.json")
CLIENT_SECRET_PATH = os.environ.get("GOOGLE_CLIENT_SECRET_PATH", "client_secret.json")


def get_oauth_credentials() -> Credentials:
    """Load or refresh OAuth credentials. Returns authorized Credentials."""
    creds = None

    # Try loading existing token
    token_path = Path(TOKEN_PATH)
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    # Also check env var for base64/JSON encoded token (for Railway)
    if creds is None:
        token_json = os.environ.get("GOOGLE_TOKEN_JSON")
        if token_json:
            import base64
            try:
                token_data = json.loads(base64.b64decode(token_json))
            except Exception:
                token_data = json.loads(token_json)
            creds = Credentials.from_authorized_user_info(token_data, SCOPES)

    # Refresh if expired
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        # Save refreshed token
        if token_path.parent.exists():
            with open(token_path, "w") as f:
                f.write(creds.to_json())

    if creds and creds.valid:
        return creds

    # No valid credentials -- need to run the auth flow
    raise RuntimeError(
        "No valid Google OAuth token found. "
        "Run 'python -m src.google_auth' to authenticate."
    )


def run_auth_flow() -> None:
    """Run the interactive OAuth flow (opens browser)."""
    secret_path = Path(CLIENT_SECRET_PATH)
    if not secret_path.exists():
        print(f"ERROR: {CLIENT_SECRET_PATH} not found.")
        print("Download it from Google Cloud Console -> Credentials -> OAuth Client ID -> Download JSON")
        return

    flow = InstalledAppFlow.from_client_secrets_file(str(secret_path), SCOPES)
    creds = flow.run_local_server(port=8095)

    # Save the token
    token_path = Path(TOKEN_PATH)
    with open(token_path, "w") as f:
        f.write(creds.to_json())

    print(f"\nAuthentication successful! Token saved to: {token_path}")
    print(f"Account: (check your browser - you just logged in)")
    print(f"\nFor Railway deployment, base64-encode token.json:")
    print(f"  [Convert]::ToBase64String([IO.File]::ReadAllBytes('{token_path.absolute()}'))")


if __name__ == "__main__":
    run_auth_flow()
