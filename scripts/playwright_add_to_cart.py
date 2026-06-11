#!/usr/bin/env python3
"""
Playwright Add-to-Cart Script (Headed - for VNC)

Opens a visible browser, logs in to GoingToCamp, finds an available site,
and adds it to cart. Run this inside a VNC session to see the browser.

Usage:
    cd ~/camply
    ~/.local/share/pipx/venvs/camply/bin/python scripts/playwright_add_to_cart.py

The browser will remain open after adding to cart so you can checkout manually.
"""

import json
import os
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

# Search parameters
START_DATE = "2026-06-19"
END_DATE = "2026-06-21"
PEOPLE = 5
TENTS = 1

# Conconully State Park for testing
CAMPGROUND_NAME = "Conconully State Park"
BASE_URL = "https://washington.goingtocamp.com"

# Build search URL
SEARCH_URL = (
    f"{BASE_URL}/create-booking/results"
    f"?transactionLocationId=NULL"
    f"&resourceLocationId=NULL"
    f"&mapId=-2147483335"  # Root map - will drill down
    f"&searchTabGroupId=0"
    f"&bookingCategoryId=0"
    f"&startDate={START_DATE}"
    f"&endDate={END_DATE}"
    f"&nights=2"
    f"&isReserving=true"
    f"&equipmentId=-32768"
    f"&subEquipmentId=-32768"
    f"&peopleCapacityCategoryCounts=%5B%5B-32767%2Cnull%2C{PEOPLE}%2Cnull%5D%5D"
    f"&searchTime=2026-06-11T00%3A00%3A00.000"
    f"&flexibleSearch=%5Bfalse%2Cfalse%2C%222026-06-01%22%2C1%5D"
)


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
        # Launch visible browser
        browser = p.chromium.launch(
            headless=False,
            args=["--start-maximized"],
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            no_viewport=True,
        )
        page = context.new_page()

        # Step 1: Navigate to site and login
        print("[1/4] Logging in...")
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        # Accept cookies if banner appears
        try:
            cookie_btn = page.locator('button:has-text("Accept"), button:has-text("OK"), button:has-text("Got it"), button:has-text("I understand"), button:has-text("Agree"), button:has-text("Continue")').first
            if cookie_btn.is_visible(timeout=3000):
                cookie_btn.click()
                time.sleep(1)
                print("  ✅ Accepted cookie banner")
        except Exception:
            pass

        # Navigate to login page
        page.goto(f"{BASE_URL}/login")
        page.wait_for_load_state("networkidle")
        time.sleep(1)

        # Fill login form
        page.fill('input[type="email"], input#email', GTC_EMAIL)
        page.fill('input[type="password"], input#password', GTC_PASSWORD)
        page.click('button[type="submit"]')
        page.wait_for_load_state("networkidle")
        time.sleep(2)
        print("  ✅ Logged in")

        # Step 2: Navigate to search
        print("[2/4] Navigating to campground search...")
        page.goto(SEARCH_URL)
        page.wait_for_load_state("networkidle")
        time.sleep(3)

        # Step 3: Navigate to Conconully and switch to List view
        print("[3/4] Finding Conconully State Park...")
        try:
            # Try clicking on Conconully in the map/navigation
            conconully_link = page.locator("text=Conconully").first
            if conconully_link.is_visible(timeout=5000):
                conconully_link.click()
                page.wait_for_load_state("networkidle")
                time.sleep(2)
                print("  ✅ Found Conconully")
            else:
                # Try Northeast region first
                ne_link = page.locator("text=Northeast").first
                if ne_link.is_visible(timeout=3000):
                    ne_link.click()
                    page.wait_for_load_state("networkidle")
                    time.sleep(2)
                    conconully_link = page.locator("text=Conconully").first
                    if conconully_link.is_visible(timeout=3000):
                        conconully_link.click()
                        page.wait_for_load_state("networkidle")
                        time.sleep(2)
                        print("  ✅ Found Conconully via Northeast")
        except Exception as e:
            print(f"  ⚠️  Navigation issue: {e}")
            print("  Continuing - you can manually navigate in the browser...")

        # Switch to List view
        print("  Switching to List view...")
        try:
            list_btn = page.locator('button:has-text("List"), [aria-label*="List"], [aria-label*="list"]').first
            if list_btn.is_visible(timeout=5000):
                list_btn.click()
                time.sleep(2)
                print("  ✅ Switched to List view")
            else:
                # Try tab/toggle that says "List"
                list_tab = page.locator('text=List').first
                if list_tab.is_visible(timeout=3000):
                    list_tab.click()
                    time.sleep(2)
                    print("  ✅ Switched to List view (via text)")
        except Exception as e:
            print(f"  ⚠️  Could not switch to List view: {e}")

        # Step 4: Find and click on an available site from the list
        print("[4/4] Looking for available sites in list...")
        time.sleep(3)

        # In list view, available sites typically have a clickable row or "Book" button
        try:
            # Look for available/bookable site in the list
            available_row = page.locator('[class*="available"], [class*="bookable"], tr:has-text("Available")').first
            if available_row.is_visible(timeout=5000):
                available_row.click()
                time.sleep(2)
                print("  ✅ Clicked on available site in list")
        except Exception:
            print("  ℹ️  Couldn't auto-click a site from list.")
            print("     Please click on an available site, then click 'Add to Stay'.")

        # Check for "Add to Stay" button
        try:
            add_button = page.locator('button#addToStay, button:has-text("Add to Stay")').first
            if add_button.is_visible(timeout=15000):
                print("\n  🎯 'Add to Stay' button found! Clicking...")
                add_button.click()
                time.sleep(3)
                print("  ✅ Clicked 'Add to Stay'!")

                # Send Telegram notification
                send_telegram(
                    f"🏕 Site added to cart!\n"
                    f"📍 {CAMPGROUND_NAME}\n"
                    f"📅 {START_DATE} to {END_DATE}\n"
                    f"👥 {PEOPLE} people, {TENTS} tent(s)\n"
                    f"🔗 {BASE_URL}/cart\n"
                    f"⏰ Go to VNC to checkout!"
                )
            else:
                print("\n  ℹ️  'Add to Stay' button not visible yet.")
                print("     Please select a site from the list, then click 'Add to Stay'.")
                send_telegram(
                    f"🏕 Browser open at {CAMPGROUND_NAME}!\n"
                    f"📅 {START_DATE} to {END_DATE}\n"
                    f"⏰ Connect to VNC to select a site and add to cart."
                )
        except Exception:
            print("\n  ℹ️  Waiting for you to manually select a site and click 'Add to Stay'.")
            send_telegram(
                f"🏕 Browser open at {CAMPGROUND_NAME}!\n"
                f"📅 {START_DATE} to {END_DATE}\n"
                f"⏰ Connect to VNC to select a site and add to cart."
            )

        print("\n" + "=" * 60)
        print("  Browser is open! You can now:")
        print("  1. Select an available site (green marker on map)")
        print("  2. Click 'Add to Stay'")
        print("  3. Proceed to checkout")
        print("")
        print("  Press Ctrl+C to close when done.")
        print("=" * 60)

        # Keep browser open indefinitely
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            print("\nClosing browser...")
            browser.close()


if __name__ == "__main__":
    main()
