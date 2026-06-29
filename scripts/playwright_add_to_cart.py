#!/usr/bin/env python3
"""
Playwright Add-to-Cart Script (Headed - for VNC)

Opens a visible browser, logs in to GoingToCamp, navigates directly to
search results via camply-generated booking URL, and adds an available
site to cart.

Usage:
    cd ~/camply
    python scripts/playwright_add_to_cart.py

    # Override via env vars (set by watcher_with_cart.py):
    CAMPLY_CAMPGROUND="Conconully" CAMPLY_START_DATE="2026-07-07" ...

The browser will remain open after adding to cart so you can checkout manually.
If no sites are available, the browser closes automatically after 10 seconds.
"""

import os
import re
import subprocess
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

# Load .env
PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# Credentials: check GTC_EMAIL first (set by watcher subprocess),
# then fall back to user-based format GTC_<user>_EMAIL
_USER = os.getenv("CAMPLY_USER", os.getenv("DEFAULT_USER", "user1"))
GTC_EMAIL = os.getenv("GTC_EMAIL") or os.getenv(f"GTC_{_USER}_EMAIL")
GTC_PASSWORD = os.getenv("GTC_PASSWORD") or os.getenv(f"GTC_{_USER}_PASSWORD")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Search parameters (from env vars if spawned by watcher, else defaults)
START_DATE = os.getenv("CAMPLY_START_DATE", "2026-07-07")
END_DATE = os.getenv("CAMPLY_END_DATE", "2026-07-09")
PEOPLE = int(os.getenv("CAMPLY_PEOPLE", "5"))
TENTS = int(os.getenv("CAMPLY_TENTS", "1"))

# Campground to search (from env var if spawned by watcher)
CAMPGROUND_NAME = os.getenv("CAMPLY_CAMPGROUND", "Conconully")

# Map tent count to subEquipmentCategoryId
TENT_IDS = {1: -32768, 2: -32767, 3: -32766}

# Campground name to ID (for camply booking-url command)
CAMPGROUND_IDS = {
    "Deception Pass": -2147483624,
    "Lake Wenatchee": -2147483594,
    "Rasar": -2147483567,
    "Lake Chelan": -2147483599,
    "Wenatchee Confluence": -2147483543,
    "Conconully": -2147483628,
}

BASE_URL = "https://washington.goingtocamp.com"
REC_AREA = 3


def generate_booking_url():
    """Generate booking URL using camply CLI."""
    campground_id = CAMPGROUND_IDS.get(CAMPGROUND_NAME)
    if not campground_id:
        print(f"  ⚠️  Unknown campground: {CAMPGROUND_NAME}, using Conconully")
        campground_id = -2147483628

    sub_equip_id = TENT_IDS.get(TENTS, -32768)

    # Find camply binary
    camply_bin = None
    for candidate in [
        os.path.expanduser("~/.local/share/pipx/venvs/camply/bin/camply"),
        os.path.expanduser("~/.local/pipx/venvs/camply/bin/camply"),
        os.path.expanduser("~/.local/bin/camply"),
    ]:
        if os.path.exists(candidate):
            camply_bin = candidate
            break
    if not camply_bin:
        camply_bin = "camply"

    cmd = [
        camply_bin, "--provider", "GoingToCamp", "booking-url",
        "--rec-area", str(REC_AREA),
        "--campground", str(campground_id),
        "--start-date", START_DATE,
        "--end-date", END_DATE,
        "--party-size", str(PEOPLE),
        "--equipment-id", str(sub_equip_id),
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        # The URL is printed as the last line of stdout (raw, for scripts)
        for line in result.stdout.strip().split("\n"):
            if line.startswith("https://"):
                return line.strip()
    except Exception as e:
        print(f"  ⚠️  Failed to generate URL via camply: {e}")

    return None


def send_telegram(message):
    """Send a Telegram notification."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    import requests
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": message},
            timeout=10,
        )
    except Exception:
        pass


def main():
    if not GTC_EMAIL or not GTC_PASSWORD:
        print("ERROR: Set GTC credentials in .env")
        sys.exit(1)

    print("=" * 60)
    print("  GoingToCamp Add-to-Cart (Playwright)")
    print("=" * 60)
    print(f"  Campground: {CAMPGROUND_NAME}")
    print(f"  Dates: {START_DATE} to {END_DATE}")
    print(f"  People: {PEOPLE}, Tents: {TENTS}")
    print("=" * 60)
    print()

    # Generate booking URL via camply
    print("[1/5] Generating booking URL...")
    booking_url = generate_booking_url()
    if not booking_url:
        print("  ❌ Failed to generate booking URL")
        sys.exit(1)
    print(f"  ✅ URL generated")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        # Step 2: Login
        print("[2/5] Logging in...")
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")
        time.sleep(1)

        # Sign in button
        page.get_by_label("Sign in to your account").click()
        page.wait_for_load_state("networkidle")
        time.sleep(1)

        # Cookie consent on login page (if shown)
        try:
            page.locator("#login-cookie-consent").click(timeout=3000)
        except Exception:
            pass

        # Fill credentials
        page.get_by_role("textbox", name="Email").fill(GTC_EMAIL)
        page.get_by_role("textbox", name="Password").fill(GTC_PASSWORD)
        page.get_by_role("button", name="Sign in", exact=True).click()
        page.wait_for_load_state("networkidle")
        time.sleep(2)
        print("  ✅ Logged in")

        # Step 3: Navigate to booking URL
        print("[3/5] Loading search results...")
        page.goto(booking_url)
        page.wait_for_load_state("networkidle")
        time.sleep(3)
        print(f"  ✅ Search results loaded")

        # Step 4: Switch to list view and select site
        print("[4/5] Finding available site...")
        try:
            page.get_by_role("radio", name="List view of results").click()
            time.sleep(2)
            print("  ✅ Switched to List view")
        except Exception:
            print("  ⚠️  Could not switch to list view")

        # Click site group (e.g. "Site Sites 1-50, Shelters 1-2")
        try:
            site_group = page.get_by_role("button", name=re.compile(r"Site\s+Sites.*")).first
            if site_group.is_visible(timeout=5000):
                site_group.click()
                time.sleep(2)
        except Exception:
            pass

        # Click first available site
        site_found = False
        try:
            available_site = page.get_by_role("button", name=re.compile(r".*Available.*")).first
            if available_site.is_visible(timeout=5000):
                site_text = available_site.inner_text()
                available_site.click()
                time.sleep(2)
                site_found = True
                print(f"  ✅ Selected: {site_text.strip()}")
        except Exception:
            pass

        if not site_found:
            print("  ❌ No available sites found.")
            print("  Site may have been taken. Closing in 10 seconds...")
            send_telegram(
                f"⚠️ Site at {CAMPGROUND_NAME} was taken before we could book.\n"
                f"📅 {START_DATE} to {END_DATE}\n"
                f"Watcher will keep trying."
            )
            time.sleep(10)
            context.close()
            browser.close()
            sys.exit(1)

        # Step 5: Reserve and confirm
        print("[5/5] Adding to cart...")
        try:
            page.get_by_role("button", name="Reserve").click()
            time.sleep(2)
            print("  ✅ Clicked 'Reserve'")

            # Checkbox
            page.get_by_role("checkbox", name="All reservation details are").check()
            time.sleep(1)
            print("  ✅ Checked confirmation")

            # Confirm
            page.get_by_role("button", name="Confirm reservation details").click()
            time.sleep(3)
            print("  ✅ Added to cart!")
            send_telegram(
                f"🏕 Site added to cart!\n"
                f"📍 {CAMPGROUND_NAME}\n"
                f"📅 {START_DATE} to {END_DATE}\n"
                f"👥 {PEOPLE} people, {TENTS} tent(s)\n"
                f"🔗 {BASE_URL}/cart\n"
                f"⏰ ~15 min to checkout! Go to VNC!"
            )
        except Exception as e:
            print(f"  ⚠️  Reserve issue: {e}")
            send_telegram(
                f"🏕 Site found at {CAMPGROUND_NAME}!\n"
                f"📅 {START_DATE} to {END_DATE}\n"
                f"⏰ Connect to VNC to complete manually."
            )

        print(f"\n{'=' * 60}")
        print("  Browser is open! Checkout when ready.")
        print("  Press Ctrl+C to close.")
        print(f"{'=' * 60}")

        # Keep browser open
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            print("\nClosing browser...")
            context.close()
            browser.close()


if __name__ == "__main__":
    main()
