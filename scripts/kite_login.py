"""Daily Zerodha Kite login — auto-captures request_token via local callback server.

Workflow:
  1. Opens your browser to the Zerodha login page automatically
  2. You log in (Zerodha redirects back with request_token in URL)
  3. Script captures the token, exchanges for access_token
  4. Saves KITE_ACCESS_TOKEN to .env (and Redis if available)

Run once each morning before market open (token expires at midnight):
    python scripts/kite_login.py

    # Or via make:
    make kite-login

Requires KITE_API_KEY and KITE_API_SECRET in .env
"""
from __future__ import annotations

import re
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from core.config import settings

# .env file lives one level up from this script (at deeptrade-ai/.env)
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"

# Port that Zerodha redirects to — must match KITE_REDIRECT_URL in .env
CALLBACK_PORT = 8000
CALLBACK_PATH = "/api/v1/auth/kite/callback"


# ──────────────────────────────────────────────
# Local HTTP server to catch the OAuth redirect
# ──────────────────────────────────────────────

class _TokenHolder:
    value: str | None = None
    event = threading.Event()


class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        token = params.get("request_token", [None])[0]

        if token:
            _TokenHolder.value = token
            body = b"<html><body><h2>Login successful - you can close this tab.</h2></body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            _TokenHolder.event.set()
        else:
            self.send_response(400)
            self.end_headers()

    def log_message(self, *_args: object) -> None:
        pass  # silence access logs


def _start_callback_server() -> HTTPServer:
    server = HTTPServer(("localhost", CALLBACK_PORT), _CallbackHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server


# ──────────────────────────────────────────────
# .env writer — updates KITE_ACCESS_TOKEN line
# ──────────────────────────────────────────────

def _save_token_to_env(token: str) -> None:
    if not ENV_FILE.exists():
        print(f"  WARNING: .env not found at {ENV_FILE}; token not saved to file.")
        return

    content = ENV_FILE.read_text()
    pattern = r"^KITE_ACCESS_TOKEN=.*$"
    replacement = f"KITE_ACCESS_TOKEN={token}"

    if re.search(pattern, content, flags=re.MULTILINE):
        new_content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
    else:
        new_content = content.rstrip("\n") + f"\n{replacement}\n"

    ENV_FILE.write_text(new_content)
    print(f"  Saved to {ENV_FILE}")


async def _save_token_to_redis(token: str) -> None:
    try:
        import redis.asyncio as aioredis
        client = aioredis.from_url(settings.redis_url)
        await client.set("kite:access_token", token, ex=8 * 3600)
        await client.aclose()
        print("  Saved to Redis (8-hour TTL)")
    except Exception as e:
        print(f"  Redis unavailable ({e}); skipping Redis save.")


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────

def main() -> int:
    if not settings.kite_api_key:
        print("ERROR: KITE_API_KEY not set in .env")
        return 1
    if not settings.kite_api_secret.get_secret_value():
        print("ERROR: KITE_API_SECRET not set in .env")
        return 1

    try:
        from kiteconnect import KiteConnect
    except ImportError:
        print("ERROR: kiteconnect not installed.  Run: pip install kiteconnect")
        return 1

    kite = KiteConnect(api_key=settings.kite_api_key)
    login_url = kite.login_url()

    print("DeepTrade AI — Kite Login")
    print(f"  Starting local callback server on port {CALLBACK_PORT}...")
    try:
        server = _start_callback_server()
    except OSError as e:
        print(f"  ERROR: Could not start server on port {CALLBACK_PORT} — {e}")
        print("  If FastAPI is already running, stop it first (Ctrl+C), then re-run this script.")
        return 1

    print(f"  Opening browser: {login_url}")
    webbrowser.open(login_url)
    print("  Waiting for Zerodha redirect (timeout: 120 seconds)...")

    got_token = _TokenHolder.event.wait(timeout=120)
    server.shutdown()

    if not got_token or not _TokenHolder.value:
        print("\nERROR: Timed out waiting for login redirect.")
        print(f"  Make sure KITE_REDIRECT_URL={settings.kite_redirect_url} is configured in your Kite app.")
        return 1

    request_token = _TokenHolder.value
    print(f"\n  request_token captured: {request_token[:8]}...")

    # Exchange for access_token
    print("  Generating session...")
    try:
        session = kite.generate_session(
            request_token,
            api_secret=settings.kite_api_secret.get_secret_value(),
        )
    except Exception as e:
        print(f"  ERROR: Session generation failed — {e}")
        return 1

    access_token: str = session["access_token"]
    user_id: str = session.get("user_id", "unknown")
    print(f"  Logged in as: {user_id}")
    print(f"  access_token: {access_token[:8]}...")

    # Persist
    print("  Saving token...")
    _save_token_to_env(access_token)

    import asyncio
    asyncio.run(_save_token_to_redis(access_token))

    print("\nLogin complete. Token valid until midnight IST.")
    print("You can now run: make fetch-data  (or start the trading engine)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
