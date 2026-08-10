#!/usr/bin/env python3
"""
Playwright Add-to-Cart Script (Headed - for VNC)

Opens a visible browser, logs in to GoingToCamp, navigates the search
UI step-by-step (select park, dates, party size, equipment), finds an
available site, and adds it to cart.

Usage:
    cd ~/camply
    python scripts/playwright_add_to_cart.py

    # Override via env vars (set by watcher_with_cart.py):
    CAMPLY_CAMPGROUND="Conconully" CAMPLY_START_DATE="2026-07-07" ...

The browser stays open after adding to cart so you can checkout manually.
"""

import os
import re
import sys
import time
from datetime import datetime
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
    print("  GoingToCamp Add-to-Cart (Playwright - UI navigation)")
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
        # Cookie consent on login page (if shown)
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

        start_dt = datetime.strptime(START_DATE, "%Y-%m-%d")
        end_dt = datetime.strptime(END_DATE, "%Y-%m-%d")
        start_day = str(start_dt.day)
        end_day = str(end_dt.day)
        # aria-labels like "July 7, 2026" (include year to avoid wrong month)
        start_aria = start_dt.strftime("%B %-d, %Y")
        end_aria = end_dt.strftime("%B %-d, %Y")

        # Open the date picker
        try:
            date_area = page.locator('mat-date-range-input, [class*="date-range"]').first
            if date_area.is_visible(timeout=3000):
                date_area.click()
                time.sleep(1)
        except Exception:
            pass

        # Click start and end dates by full aria-label
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
            print(f"  ⚠️  Date selection issue: {e}")
            print("     Please select dates manually in the browser.")

        # Set number of people. The default value varies, so normalize first:
        # click "Remove one" repeatedly to floor at the minimum (1), then
        # "Add one" (PEOPLE - 1) times. Extra Remove clicks at the floor are
        # harmless no-ops. This is deterministic regardless of the default.
        try:
            for _ in range(15):  # floor to minimum (usually 1)
                try:
                    remove_btn = page.get_by_role("button", name="Remove one").first
                    if remove_btn.is_disabled():
                        break
                    remove_btn.click()
                    time.sleep(0.1)
                except Exception:
                    break
            # Now at minimum (assume 1). Add up to target.
            for _ in range(PEOPLE - 1):
                page.get_by_role("button", name="Add one").click()
                time.sleep(0.2)
            print(f"  ✅ Set party size to {PEOPLE}")
        except Exception as e:
            print(f"  ⚠️  Party size issue: {e}")

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
        try:
            page.get_by_role("radio", name="List view of results").click()
            time.sleep(2)
            print("  ✅ Switched to List view")
        except Exception:
            print("  ⚠️  Could not switch to list view")

        # Site selection handles 3 layouts:
        #   Conconully:     group "Site Sites 1-50" -> site "Site 2 Available"
        #   Lake Wenatchee: sub-area "Site South Campground" -> View more -> "Site 23 Available"
        #   Deception Pass: sub-area "Site Forest Loop Available" -> "Site 13 Available" -> Acknowledge
        #
        # Key distinction:
        #   Sub-area/group header = "Site <TEXT>"   (e.g. Forest Loop, South Campground, Sites 1-50)
        #   Individual site       = "Site <NUMBER>" (e.g. Site 13, Site 2)
        # A sub-area may itself contain "Available", so we can't use that to tell them apart.

        # Regex: sub-area = "Site " followed by a non-digit; site = "Site " followed by digits
        SUBAREA_RE = re.compile(r"^Site\s+(?!\d)")
        SITE_RE = re.compile(r"^Site\s+\d+\b.*Available")

        # Step A: If there's a sub-area/group header, click it (prefer one marked Available)
        try:
            subareas = page.get_by_role("button", name=SUBAREA_RE).all()
            chosen = None
            for btn in subareas:
                try:
                    if not btn.is_visible():
                        continue
                    label = btn.inner_text().strip()
                    if "Available" in label:
                        chosen = (btn, label)
                        break
                    if chosen is None:
                        chosen = (btn, label)
                except Exception:
                    continue
            if chosen:
                chosen[0].click()
                time.sleep(2)
                print(f"  ✅ Opened sub-area/group: {chosen[1].splitlines()[0]}")
        except Exception:
            pass

        # Step B: Click "View more" to reveal all sites (some multi-sub-area parks)
        try:
            view_more = page.get_by_role("button", name="View more").first
            if view_more.is_visible(timeout=3000):
                view_more.click()
                time.sleep(1)
                print("  ✅ Clicked 'View more'")
        except Exception:
            pass

        # Step C: Click first individual available site ("Site <NUMBER> ... Available")
        site_found = False
        try:
            available_site = page.get_by_role("button", name=SITE_RE).first
            if available_site.is_visible(timeout=5000):
                site_name = available_site.inner_text()
                available_site.click()
                time.sleep(2)
                site_found = True
                print(f"  ✅ Selected available site: {site_name.splitlines()[0].strip()}")
        except Exception as e:
            print(f"  ⚠️  Could not auto-select numbered site: {e}")

        # Fallback: if no numbered site matched, try any "Available" button that
        # is NOT a sub-area header (in case a park uses a different naming)
        if not site_found:
            try:
                candidates = page.get_by_role("button", name=re.compile(r".*Available.*")).all()
                for btn in candidates:
                    try:
                        label = btn.inner_text().strip()
                        if SUBAREA_RE.match(label):
                            continue  # skip sub-area headers
                        if btn.is_visible():
                            btn.click()
                            time.sleep(2)
                            site_found = True
                            print(f"  ✅ Selected available site (fallback): {label.splitlines()[0].strip()}")
                            break
                    except Exception:
                        continue
            except Exception:
                pass

        if not site_found:
            print("  ❌ No available sites found. Site may have been taken.")
            print("  Closing in 10 seconds...")
            send_telegram(
                f"⚠️ Site at {CAMPGROUND_NAME} was taken before we could book.\n"
                f"📅 {START_DATE} to {END_DATE}\n"
                f"Watcher will keep trying."
            )
            time.sleep(10)
            context.close()
            browser.close()
            sys.exit(1)

        # Step 6: Reserve / Add to cart
        print("[6/6] Adding to cart...")
        try:
            page.get_by_role("button", name="Reserve").click()
            time.sleep(2)
            print("  ✅ Clicked 'Reserve'")

            # Handle optional "Acknowledge" popup (can appear on any campground)
            try:
                ack_btn = page.get_by_role("button", name="Acknowledge")
                if ack_btn.is_visible(timeout=3000):
                    ack_btn.click()
                    time.sleep(1)
                    print("  ✅ Acknowledged popup")
            except Exception:
                pass

            # Check the "All reservation details are correct" checkbox
            try:
                page.get_by_role("checkbox", name="All reservation details are").check()
                time.sleep(1)
                print("  ✅ Checked confirmation")
            except Exception:
                # Fallback to text click
                try:
                    page.get_by_text("All reservation details are").click(timeout=3000)
                    time.sleep(1)
                except Exception:
                    pass

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
                f"⏰ Connect to VNC to finish adding to cart."
            )

        print(f"\n{'=' * 60}")
        print("  Browser is open! Checkout when ready.")
        print("  Close browser window or press Ctrl+C to exit.")
        print(f"{'=' * 60}")

        # Keep alive until browser is closed or Ctrl+C
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
