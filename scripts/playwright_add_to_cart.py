#!/usr/bin/env python3
"""
Playwright Add-to-Cart Script (Headed - for VNC)

Opens a visible browser, logs in to GoingToCamp, finds an available site,
and adds it to cart. Run this inside a VNC session to see the browser.

Usage:
    cd ~/camply
    python scripts/playwright_add_to_cart.py

The browser will remain open after adding to cart so you can checkout manually.
"""

import os
import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

# Load .env
PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")

GTC_EMAIL = os.getenv("GTC_EMAIL")
GTC_PASSWORD = os.getenv("GTC_PASSWORD")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Search parameters (from campgrounds.conf)
START_DATE = "2026-06-19"
END_DATE = "2026-06-21"
PEOPLE = 5
TENTS = 1

# Campground to search
CAMPGROUND_NAME = "Conconully"

BASE_URL = "https://washington.goingtocamp.com"

# Tent option labels
TENT_OPTIONS = {
    1: "1 Tent",
    2: "2 Tents",
    3: "3 Tents",
}


def send_telegram(message):
    """Send a Telegram notification."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("  [Telegram not configured]")
        return
    import requests
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        json={"chat_id": TELEGRAM_CHAT_ID, "text": message},
    )
    print("  📱 Telegram notification sent")


def main():
    if not GTC_EMAIL or not GTC_PASSWORD:
        print("ERROR: Set GTC_EMAIL and GTC_PASSWORD in .env")
        sys.exit(1)

    print("=" * 60)
    print("  GoingToCamp Add-to-Cart (Playwright - Headed)")
    print("=" * 60)
    print(f"  Campground: {CAMPGROUND_NAME}")
    print(f"  Dates: {START_DATE} to {END_DATE}")
    print(f"  People: {PEOPLE}, Tents: {TENTS}")
    print("=" * 60)
    print()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        # Step 1: Accept cookies
        print("[1/6] Loading site and accepting cookies...")
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")
        try:
            page.get_by_role("button", name="I Consent").click(timeout=5000)
            print("  ✅ Accepted cookies")
        except Exception:
            print("  ℹ️  No cookie banner (already accepted)")

        # Step 2: Login
        print("[2/6] Logging in...")
        page.get_by_role("button", name="Sign in to your account").click()
        page.wait_for_load_state("networkidle")
        time.sleep(1)
        page.get_by_role("textbox", name="Email").fill(GTC_EMAIL)
        page.get_by_role("textbox", name="Password").fill(GTC_PASSWORD)
        page.get_by_role("button", name="Sign in", exact=True).click()
        page.wait_for_load_state("networkidle")
        time.sleep(2)
        print("  ✅ Logged in")

        # Step 3: Start reservation search
        print("[3/6] Starting reservation search...")
        page.get_by_role("button", name="Create reservation").click()
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        # Select park
        page.get_by_role("combobox", name="Select park").click()
        page.get_by_role("combobox", name="Select park").fill(CAMPGROUND_NAME[:3].lower())
        time.sleep(1)
        page.get_by_role("option", name=CAMPGROUND_NAME).click()
        time.sleep(1)
        print(f"  ✅ Selected {CAMPGROUND_NAME}")

        # Step 4: Set dates and party size
        print("[4/6] Setting dates and party size...")

        # Parse start/end dates to find the right buttons
        from datetime import datetime
        start_dt = datetime.strptime(START_DATE, "%Y-%m-%d")
        end_dt = datetime.strptime(END_DATE, "%Y-%m-%d")
        start_label = start_dt.strftime("%B %-d,")  # e.g. "June 19,"
        end_label = end_dt.strftime("%B %-d,")      # e.g. "June 21,"

        # Click on the date area to open calendar, then select dates
        try:
            page.get_by_role("button", name=start_label).click(timeout=5000)
            time.sleep(0.5)
            page.get_by_role("button", name=end_label).click()
            time.sleep(0.5)
            print(f"  ✅ Selected dates: {START_DATE} to {END_DATE}")
        except Exception as e:
            print(f"  ⚠️  Date selection issue: {e}")
            print("     You may need to navigate to the right month manually.")

        # Set number of people (default is 2, click "Add one" to increase)
        add_people_clicks = PEOPLE - 2  # default starts at 2
        if add_people_clicks > 0:
            for _ in range(add_people_clicks):
                page.get_by_role("button", name="Add one").click()
                time.sleep(0.3)
            print(f"  ✅ Set party size to {PEOPLE}")

        # Select tent equipment
        tent_label = TENT_OPTIONS.get(TENTS, "1 Tent")
        try:
            page.locator("#equipment-field-wrapper > .mat-mdc-text-field-wrapper > .mat-mdc-form-field-flex").click()
            time.sleep(0.5)
            page.get_by_role("option", name=tent_label).click()
            time.sleep(0.5)
            print(f"  ✅ Selected equipment: {tent_label}")
        except Exception as e:
            print(f"  ⚠️  Equipment selection issue: {e}")

        # Step 5: Search and find site
        print("[5/6] Searching for availability...")
        page.get_by_role("button", name="Search for availability").click()
        page.wait_for_load_state("networkidle")
        time.sleep(3)

        # Switch to list view
        page.get_by_role("radio", name="List view of results").click()
        time.sleep(2)
        print("  ✅ Switched to List view")

        # Click on a site group that has availability
        try:
            # Look for a site group button (like "Site Sites 1-50...")
            site_group = page.locator('button[class*="site"], button:has-text("Site")').first
            if site_group.is_visible(timeout=5000):
                site_group.click()
                time.sleep(2)
        except Exception:
            pass

        # Find and click first available site
        try:
            available_site = page.get_by_role("button", name=re.compile(r".*Available.*")).first
            if available_site.is_visible(timeout=5000):
                site_name = available_site.inner_text()
                available_site.click()
                time.sleep(2)
                print(f"  ✅ Selected available site: {site_name.strip()}")
        except Exception as e:
            print(f"  ⚠️  Could not auto-select site: {e}")
            print("     Please click an available site manually.")

        # Step 6: Reserve / Add to cart
        print("[6/6] Adding to cart...")
        try:
            reserve_btn = page.get_by_role("button", name="Reserve")
            if reserve_btn.is_visible(timeout=10000):
                reserve_btn.click()
                time.sleep(2)
                print("  ✅ Clicked 'Reserve'")

                # Confirm reservation details
                try:
                    confirm_btn = page.get_by_role("button", name="Confirm reservation details")
                    if confirm_btn.is_visible(timeout=10000):
                        confirm_btn.click()
                        time.sleep(3)
                        print("  ✅ Confirmed reservation details!")

                        send_telegram(
                            f"🏕 Site added to cart!\n"
                            f"📍 {CAMPGROUND_NAME}\n"
                            f"📅 {START_DATE} to {END_DATE}\n"
                            f"👥 {PEOPLE} people, {TENTS} tent(s)\n"
                            f"🔗 {BASE_URL}/cart\n"
                            f"⏰ Go to VNC to checkout!"
                        )
                except Exception as e:
                    print(f"  ⚠️  Confirm step issue: {e}")
            else:
                print("  ⚠️  'Reserve' button not found. Please click manually.")
        except Exception as e:
            print(f"  ⚠️  Reserve issue: {e}")
            send_telegram(
                f"🏕 Browser open at {CAMPGROUND_NAME}!\n"
                f"📅 {START_DATE} to {END_DATE}\n"
                f"⏰ Connect to VNC to finish adding to cart."
            )

        print("\n" + "=" * 60)
        print("  Browser is open! You can:")
        print("  1. Verify the cart")
        print("  2. Proceed to checkout/payment")
        print("")
        print("  Press Ctrl+C to close when done.")
        print("=" * 60)

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
