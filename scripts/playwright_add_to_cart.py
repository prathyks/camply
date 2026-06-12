#!/usr/bin/env python3
"""
Playwright Add-to-Cart Script (Headed - for VNC)

Opens a visible browser, logs in to GoingToCamp, navigates directly to
search results via pre-built URL, and adds an available site to cart.

Usage:
    cd ~/camply
    python scripts/playwright_add_to_cart.py

    # Override via env vars (set by watcher_with_cart.py):
    CAMPLY_CAMPGROUND="Conconully" CAMPLY_START_DATE="2026-06-19" ...

The browser will remain open after adding to cart so you can checkout manually.
If no sites are available, the browser closes automatically after 30 seconds.
"""

import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

# Load .env
PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")

GTC_EMAIL = os.getenv("GTC_EMAIL")
GTC_PASSWORD = os.getenv("GTC_PASSWORD")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Search parameters (from env vars if spawned by watcher, else defaults)
START_DATE = os.getenv("CAMPLY_START_DATE", "2026-06-19")
END_DATE = os.getenv("CAMPLY_END_DATE", "2026-06-21")
PEOPLE = int(os.getenv("CAMPLY_PEOPLE", "5"))
TENTS = int(os.getenv("CAMPLY_TENTS", "1"))

# Campground to search (from env var if spawned by watcher)
CAMPGROUND_NAME = os.getenv("CAMPLY_CAMPGROUND", "Conconully")

BASE_URL = "https://washington.goingtocamp.com"

# Map tent count to subEquipmentCategoryId
TENT_IDS = {1: -32768, 2: -32767, 3: -32766}

# Campground name to mapId (root map for search results page)
# These are the parent maps that show all sub-areas for each park
CAMPGROUND_MAP_IDS = {
    "Deception Pass": -2147483388,
    "Lake Wenatchee": -2147483375,
    "Rasar": -2147483362,
    "Lake Chelan": -2147483377,
    "Wenatchee Confluence": -2147483349,
    "Conconully": -2147483391,
}


def build_search_url():
    """Build the direct search results URL with all parameters pre-filled."""
    map_id = CAMPGROUND_MAP_IDS.get(CAMPGROUND_NAME, -2147483335)
    sub_equip_id = TENT_IDS.get(TENTS, -32768)
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000")

    # peopleCapacityCategoryCounts format: [[-32767,null,count,null]]
    people_param = quote(f"[[-32767,null,{PEOPLE},null]]")
    # filterData: exclude ADA-only and Equestrian sites
    filter_data = quote('{"-32759":"[[1],0,0,0]","-32708":"[[1],0,0,0]"}')

    url = (
        f"{BASE_URL}/create-booking/results"
        f"?transactionLocationId=NULL"
        f"&resourceLocationId=NULL"
        f"&mapId={map_id}"
        f"&searchTabGroupId=0"
        f"&bookingCategoryId=0"
        f"&startDate={START_DATE}"
        f"&endDate={END_DATE}"
        f"&nights={int((datetime.strptime(END_DATE, '%Y-%m-%d') - datetime.strptime(START_DATE, '%Y-%m-%d')).days)}"
        f"&isReserving=true"
        f"&equipmentId=-32768"
        f"&subEquipmentId={sub_equip_id}"
        f"&peopleCapacityCategoryCounts={people_param}"
        f"&searchTime={quote(now)}"
        f"&flexibleSearch={quote('[false,false,\"' + START_DATE[:7] + '-01\",1]')}"
        f"&filterData={filter_data}"
    )
    return url


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
        print("ERROR: Set GTC_EMAIL and GTC_PASSWORD in .env")
        sys.exit(1)

    search_url = build_search_url()

    print("=" * 60)
    print("  GoingToCamp Add-to-Cart (Fast Direct URL)")
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

        # Step 1: Accept cookies + Login
        print("[1/4] Logging in...")
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")
        try:
            page.get_by_role("button", name="I Consent").click(timeout=5000)
        except Exception:
            pass

        page.get_by_role("button", name="Sign in to your account").click()
        page.wait_for_load_state("networkidle")
        time.sleep(1)
        page.get_by_role("textbox", name="Email").fill(GTC_EMAIL)
        page.get_by_role("textbox", name="Password").fill(GTC_PASSWORD)
        page.get_by_role("button", name="Sign in", exact=True).click()
        page.wait_for_load_state("networkidle")
        time.sleep(2)
        print("  ✅ Logged in")

        # Step 2: Go directly to search results URL (skip form filling)
        print("[2/4] Navigating to search results...")
        page.goto(search_url)
        page.wait_for_load_state("networkidle")
        time.sleep(3)
        print(f"  ✅ Loaded search results for {CAMPGROUND_NAME}")

        # Step 3: Switch to list view and select first available site
        print("[3/4] Finding available site...")
        try:
            page.get_by_role("radio", name="List view of results").click()
            time.sleep(2)
            print("  ✅ Switched to List view")
        except Exception:
            print("  ⚠️  Could not switch to list view")

        # Click site group if present
        try:
            site_group = page.get_by_role("button", name=re.compile(r"Site.*")).first
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
            print("  ❌ No available sites found in list.")
            print("  Site may have been taken. Closing browser in 10 seconds...")
            send_telegram(
                f"⚠️ Site at {CAMPGROUND_NAME} was taken before we could book.\n"
                f"📅 {START_DATE} to {END_DATE}\n"
                f"Watcher will keep trying."
            )
            time.sleep(10)
            context.close()
            browser.close()
            sys.exit(1)

        # Step 4: Reserve and confirm
        print("[4/4] Adding to cart...")
        try:
            reserve_btn = page.get_by_role("button", name="Reserve")
            if reserve_btn.is_visible(timeout=10000):
                reserve_btn.click()
                time.sleep(2)
                print("  ✅ Clicked 'Reserve'")

                # Checkbox
                try:
                    page.get_by_text("All reservation details are").click(timeout=5000)
                    time.sleep(1)
                    print("  ✅ Checked confirmation")
                except Exception:
                    pass

                # Confirm
                try:
                    page.get_by_role("button", name="Confirm reservation details").click(timeout=10000)
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
                    print(f"  ⚠️  Confirm issue: {e}")
            else:
                print("  ⚠️  'Reserve' button not found.")
                send_telegram(
                    f"⚠️ Found site at {CAMPGROUND_NAME} but couldn't reserve.\n"
                    f"📅 {START_DATE} to {END_DATE}\n"
                    f"⏰ Connect to VNC to complete manually."
                )
        except Exception as e:
            print(f"  ⚠️  Reserve issue: {e}")

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
