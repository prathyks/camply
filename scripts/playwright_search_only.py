#!/usr/bin/env python3
"""
Playwright Search-Only Script (Headed - for VNC)

Logs in to GoingToCamp and navigates the search UI up to the results
page, then LEAVES THE BROWSER OPEN for the user to manually select a
site and complete the booking.

Useful for:
- Observing the site-selection UI for multi-sub-area parks
- Letting the automation handle the tedious login + search, then the
  user does the final site pick + add to cart

Usage:
    cd ~/camply
    python scripts/playwright_search_only.py

    # Override via env vars:
    CAMPLY_CAMPGROUND="Lake Wenatchee" CAMPLY_START_DATE="2026-08-20" ...
"""

import os
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

# Load .env
PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")

_USER = os.getenv("CAMPLY_USER", os.getenv("DEFAULT_USER", "user1"))
GTC_EMAIL = os.getenv("GTC_EMAIL") or os.getenv(f"GTC_{_USER}_EMAIL")
GTC_PASSWORD = os.getenv("GTC_PASSWORD") or os.getenv(f"GTC_{_USER}_PASSWORD")

START_DATE = os.getenv("CAMPLY_START_DATE", "2026-08-20")
END_DATE = os.getenv("CAMPLY_END_DATE", "2026-08-22")
PEOPLE = int(os.getenv("CAMPLY_PEOPLE", "5"))
TENTS = int(os.getenv("CAMPLY_TENTS", "1"))
CAMPGROUND_NAME = os.getenv("CAMPLY_CAMPGROUND", "Lake Wenatchee")

BASE_URL = "https://washington.goingtocamp.com"

TENT_OPTIONS = {1: "1 Tent", 2: "2 Tents", 3: "3 Tents"}


def main():
    if not GTC_EMAIL or not GTC_PASSWORD:
        print("ERROR: Set GTC credentials in .env")
        sys.exit(1)

    print("=" * 60)
    print("  GoingToCamp Search-Only (login + search, then hand off)")
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
        print("[1/5] Loading site and accepting cookies...")
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")
        try:
            page.get_by_role("button", name="I Consent").click(timeout=5000)
            print("  ✅ Accepted cookies")
        except Exception:
            print("  ℹ️  No cookie banner")

        # Step 2: Login
        print("[2/5] Logging in...")
        page.get_by_role("button", name="Sign in to your account").click()
        page.wait_for_load_state("networkidle")
        time.sleep(1)
        try:
            page.locator("#login-cookie-consent").click(timeout=3000)
        except Exception:
            pass
        page.get_by_role("textbox", name="Email").fill(GTC_EMAIL)
        page.get_by_role("textbox", name="Password").fill(GTC_PASSWORD)
        page.get_by_role("button", name="Sign in", exact=True).click()
        page.wait_for_load_state("networkidle")
        time.sleep(2)
        print("  ✅ Logged in")

        # Step 3: Start reservation search
        print("[3/5] Starting reservation search...")
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

        # Step 4: Dates, party, equipment
        print("[4/5] Setting dates and party size...")
        start_dt = datetime.strptime(START_DATE, "%Y-%m-%d")
        end_dt = datetime.strptime(END_DATE, "%Y-%m-%d")
        start_day = str(start_dt.day)
        end_day = str(end_dt.day)
        start_aria = start_dt.strftime("%B %-d, %Y")
        end_aria = end_dt.strftime("%B %-d, %Y")

        try:
            date_area = page.locator('mat-date-range-input, [class*="date-range"]').first
            if date_area.is_visible(timeout=3000):
                date_area.click()
                time.sleep(1)
        except Exception:
            pass

        try:
            start_btn = page.locator(f'button[aria-label*="{start_aria}"], button:has-text("{start_aria}")').first
            if start_btn.is_visible(timeout=3000):
                start_btn.click()
                time.sleep(0.5)
            else:
                page.get_by_role("button", name=f"{start_dt.strftime('%B')} {start_day},").first.click()
                time.sleep(0.5)

            end_btn = page.locator(f'button[aria-label*="{end_aria}"], button:has-text("{end_aria}")').first
            if end_btn.is_visible(timeout=3000):
                end_btn.click()
                time.sleep(0.5)
            else:
                page.get_by_role("button", name=f"{end_dt.strftime('%B')} {end_day},").first.click()
                time.sleep(0.5)
            print(f"  ✅ Selected dates: {START_DATE} to {END_DATE}")
        except Exception as e:
            print(f"  ⚠️  Date selection issue: {e} - set manually if needed")

        add_people_clicks = PEOPLE - 2
        if add_people_clicks > 0:
            for _ in range(add_people_clicks):
                page.get_by_role("button", name="Add one").click()
                time.sleep(0.3)
            print(f"  ✅ Set party size to {PEOPLE}")

        tent_label = TENT_OPTIONS.get(TENTS, "1 Tent")
        try:
            page.locator("#equipment-field-wrapper > .mat-mdc-text-field-wrapper > .mat-mdc-form-field-flex").click()
            time.sleep(0.5)
            page.get_by_role("option", name=tent_label).click()
            time.sleep(0.5)
            print(f"  ✅ Selected equipment: {tent_label}")
        except Exception as e:
            print(f"  ⚠️  Equipment selection issue: {e}")

        # Step 5: Search, then hand off to user
        print("[5/5] Searching for availability...")
        page.get_by_role("button", name="Search for availability").click()
        page.wait_for_load_state("networkidle")
        time.sleep(3)

        # Try switching to list view for convenience
        try:
            page.get_by_role("radio", name="List view of results").click()
            time.sleep(1)
            print("  ✅ Switched to List view")
        except Exception:
            pass

        print(f"\n{'=' * 60}")
        print("  ✋ HANDING OFF TO YOU")
        print("  The browser is on the search results page.")
        print("  Now manually:")
        print("    1. Expand the sub-area / campground (North/South etc)")
        print("    2. Click an available site")
        print("    3. Reserve → check confirmation → Confirm")
        print("")
        print("  Close browser window or press Ctrl+C when done.")
        print(f"{'=' * 60}")

        # Keep alive until browser closed / Ctrl+C
        try:
            while True:
                if not browser.contexts:
                    print("\n  Browser closed by user.")
                    break
                try:
                    page.evaluate("1")
                except Exception:
                    print("\n  Browser window closed.")
                    break
                time.sleep(5)
        except KeyboardInterrupt:
            print("\nClosing browser...")
        finally:
            try:
                context.close()
            except Exception:
                pass
            try:
                browser.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
