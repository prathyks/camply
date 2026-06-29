#!/usr/bin/env python3
"""
Campsite Watcher + Auto Add-to-Cart

Integrated script that:
1. Monitors GoingToCamp campgrounds for availability using camply
2. When a site is found, launches Playwright to add it to cart
3. Sends Telegram notification
4. Keeps browser open for checkout

Usage (run from VNC terminal):
    cd ~/camply
    python scripts/watcher_with_cart.py

    # With a specific campground (overrides campgrounds.conf):
    python scripts/watcher_with_cart.py --campground "Conconully"

    # Dry run (just check availability, don't add to cart):
    python scripts/watcher_with_cart.py --dry-run
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import threading
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv

# Load .env
PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Default user (overridden by --user argument, or set DEFAULT_USER in .env)
DEFAULT_USER = os.getenv("DEFAULT_USER", "user1")


def get_user_credentials(username):
    """Get GTC credentials for the specified user from .env."""
    email = os.getenv(f"GTC_{username}_EMAIL")
    password = os.getenv(f"GTC_{username}_PASSWORD")
    if not email or not password:
        # Fallback to legacy format (GTC_EMAIL / GTC_PASSWORD)
        if username == DEFAULT_USER:
            email = email or os.getenv("GTC_EMAIL")
            password = password or os.getenv("GTC_PASSWORD")
    return email, password

BASE_URL = "https://washington.goingtocamp.com"

# Tent option labels
TENT_OPTIONS = {
    1: "1 Tent",
    2: "2 Tents",
    3: "3 Tents",
}

# Campground name map (GoingToCamp IDs to search names)
CAMPGROUND_NAMES = {
    "-2147483624": "Deception Pass",
    "-2147483594": "Lake Wenatchee",
    "-2147483567": "Rasar",
    "-2147483599": "Lake Chelan",
    "-2147483543": "Wenatchee Confluence",
    "-2147483628": "Conconully",
}


def load_config():
    """Load search parameters from campgrounds.conf."""
    conf_file = PROJECT_ROOT / "campgrounds.conf"
    config = {}
    campgrounds = []

    recdotgov_campgrounds = []

    with open(conf_file) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line and "|" not in line:
                key, val = line.split("=", 1)
                config[key] = val
            elif line.startswith("GoingToCamp|"):
                parts = line.split("|")
                campgrounds.append({
                    "provider": parts[0],
                    "rec_area": parts[1],
                    "id": parts[2],
                    "name": parts[3] if len(parts) > 3 else "",
                })
            elif line.startswith("RecreationDotGov|"):
                parts = line.split("|")
                recdotgov_campgrounds.append({
                    "provider": parts[0],
                    "id": parts[1],
                    "name": parts[2] if len(parts) > 2 else "",
                })

    return {
        "start_date": config.get("START_DATE", "2026-06-19"),
        "end_date": config.get("END_DATE", "2026-06-22"),
        "nights": int(config.get("NIGHTS", "2")),
        "polling_interval": int(config.get("POLLING_INTERVAL", "10")),
        "people": int(config.get("PEOPLE", "5")),
        "tents": int(config.get("TENTS", "1")),
        "campgrounds": campgrounds,
        "recdotgov_campgrounds": recdotgov_campgrounds,
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


def _check_consecutive_availability(avails, min_nights, start_date_str=None):
    """
    Check if any resource has min_nights consecutive available nights.

    The availability array includes the checkout day as the last entry,
    which is NOT a bookable night. Only check entries [0..n-2] for bookable
    nights (last entry is checkout day status).

    Returns list of available resource dicts with consecutive night count
    and actual available date range, or empty list if none found.
    """
    from datetime import timedelta

    available_sites = []
    start_date = datetime.strptime(start_date_str, "%Y-%m-%d") if start_date_str else None

    for rid, days in avails.items():
        if isinstance(days, list):
            # Exclude the last entry (checkout day) - only bookable nights matter
            bookable_days = days[:-1] if len(days) > 1 else days
            consecutive = 0
            best_run_start = 0
            best_run_length = 0
            current_run_start = 0

            for i, day in enumerate(bookable_days):
                if isinstance(day, dict) and day.get("availability") == 0:
                    if consecutive == 0:
                        current_run_start = i
                    consecutive += 1
                    if consecutive > best_run_length:
                        best_run_length = consecutive
                        best_run_start = current_run_start
                else:
                    consecutive = 0

            if best_run_length >= min_nights:
                site_info = {
                    "resourceId": int(rid),
                    "consecutive_nights": best_run_length,
                }
                # Calculate actual available dates
                if start_date:
                    avail_start = start_date + timedelta(days=best_run_start)
                    avail_end = avail_start + timedelta(days=best_run_length)
                    site_info["avail_start"] = avail_start.strftime("%Y-%m-%d")
                    site_info["avail_end"] = avail_end.strftime("%Y-%m-%d")
                available_sites.append(site_info)
    return available_sites


def check_recdotgov_availability(config, campground_name=None):
    """
    Check availability for Recreation.gov campgrounds using camply CLI.
    Returns list of available campground dicts.
    """
    recdotgov = config.get("recdotgov_campgrounds", [])
    if not recdotgov:
        return []

    if campground_name:
        recdotgov = [cg for cg in recdotgov if campground_name.lower() in cg["name"].lower()]

    if not recdotgov:
        return []

    # Build camply command
    cg_args = []
    for cg in recdotgov:
        cg_args.extend(["--campground", cg["id"]])

    camply_bin = os.path.expanduser("~/.local/share/pipx/venvs/camply/bin/camply")
    if not os.path.exists(camply_bin):
        camply_bin = "camply"

    cmd = [
        camply_bin, "campsites",
        *cg_args,
        "--start-date", config["start_date"],
        "--end-date", config["end_date"],
        "--nights", str(config["nights"]),
        "--search-once",
        "--notifications", "silent",
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120,
                                env={**os.environ, "TELEGRAM_BOT_TOKEN": "", "TELEGRAM_CHAT_ID": ""})
        output = result.stdout + result.stderr

        # Check if camply found any sites (look for campsite match indicators)
        if "Matching Campsites Found" in output and "0 Matching Campsites" not in output:
            # Try to identify which campground had availability
            for cg in recdotgov:
                if cg["id"] in output or cg["name"].split("(")[0].strip().lower() in output.lower():
                    print(f"  ✅ {cg['name']}: AVAILABLE! (Recreation.gov)")
                    return [cg]
            # Couldn't identify which, return first
            print(f"  ✅ Recreation.gov: AVAILABLE!")
            return [recdotgov[0]]
        else:
            for cg in recdotgov:
                print(f"  ❌ {cg['name']}: No availability (Recreation.gov)")
    except subprocess.TimeoutExpired:
        print("  ⚠️  Recreation.gov check timed out")
    except Exception as e:
        print(f"  ⚠️  Recreation.gov check error: {e}")

    return []


def check_availability(config, campground_name=None, gtc_email=None, gtc_password=None):
    """
    Check availability using camply's GoingToCamp provider via API.
    Returns list of available campground dicts.
    """
    import requests
    from fake_useragent import UserAgent

    session = requests.Session()
    session.headers.update({
        "User-Agent": UserAgent(browsers=["chrome"]).random,
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "app-version": "5.110.184",
        "app-language": "en-US",
    })

    def get_latest_xsrf():
        for c in session.cookies:
            if "XSRF" in c.name:
                return c.value
        return ""

    # Init session
    session.get(BASE_URL)
    session.post(f"{BASE_URL}/api/config/features", json=["AccountDeletion"])
    session.headers["x-xsrf-token"] = get_latest_xsrf()

    # Login
    session.post(f"{BASE_URL}/api/auth/login",
                 json={"email": gtc_email, "password": gtc_password})
    session.headers["x-xsrf-token"] = get_latest_xsrf()

    # Get cart (needed for availability check)
    cart = session.get(f"{BASE_URL}/api/cart").json()
    session.headers["x-xsrf-token"] = get_latest_xsrf()

    # Get maps to find campground mapIds
    maps_resp = session.get(f"{BASE_URL}/api/maps")
    session.headers["x-xsrf-token"] = get_latest_xsrf()
    maps = maps_resp.json()

    # Build campground ID -> mapId lookup
    cg_map_ids = {}
    for m in maps:
        for link in m.get("mapLinks", []):
            rl_id = link.get("resourceLocationId")
            if rl_id:
                cg_map_ids[str(rl_id)] = link.get("childMapId")

    # Filter campgrounds to check
    campgrounds_to_check = config["campgrounds"]
    if campground_name:
        campgrounds_to_check = [
            cg for cg in campgrounds_to_check
            if campground_name.lower() in cg["name"].lower()
        ]

    available_campgrounds = []

    for i, cg in enumerate(campgrounds_to_check):
        cg_id = cg["id"]
        map_id = cg_map_ids.get(cg_id)
        if not map_id:
            continue

        # 5s delay between campground checks
        if i > 0:
            time.sleep(5)

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        params = {
            "mapId": map_id,
            "bookingCategoryId": 0,
            "startDate": config["start_date"],
            "endDate": config["end_date"],
            "isReserving": "true",
            "getDailyAvailability": "true",
            "equipmentCategoryId": -32768,
            "subEquipmentCategoryId": TENT_OPTIONS_IDS.get(config["tents"], -32768),
            "numEquipment": 0,
            "boatLength": 0,
            "boatDraft": 0,
            "boatWidth": 0,
            "cartUid": cart.get("cartUid", ""),
            "cartTransactionUid": cart.get("createTransactionUid", ""),
            "bookingUid": str(uuid4()),
            "seed": now,
            "peopleCapacityCategoryCounts": json.dumps(
                [{"capacityCategoryId": -32767, "subCapacityCategoryId": None, "count": config["people"]}]
            ),
            "filterData": json.dumps([
                {"attributeDefinitionId": -32759, "attributeDefinitionDecimalValue": 0, "enumValues": [1], "filterStrategy": 0, "attributeType": 0},
                {"attributeDefinitionId": -32708, "attributeDefinitionDecimalValue": 0, "enumValues": [1], "filterStrategy": 0, "attributeType": 0},
            ]),
        }

        resp = session.get(f"{BASE_URL}/api/availability/map", params=params)
        session.headers["x-xsrf-token"] = get_latest_xsrf()

        if resp.status_code != 200:
            continue

        data = resp.json()
        avails = data.get("resourceAvailabilities", {})
        map_link_avails = data.get("mapLinkAvailabilities", {})

        # Check direct resource availability (0 = available for consecutive nights)
        found_sites = _check_consecutive_availability(avails, config["nights"], start_date_str=config["start_date"])

        # If no direct resources but sub-maps exist, drill into each sub-map
        if not found_sites and map_link_avails:
            for sub_map_id, avail_status in map_link_avails.items():
                # avail_status is a list like [0] or [5] where 0 = has availability
                if not isinstance(avail_status, list) or 0 not in avail_status:
                    continue
                # Drill into this sub-map to verify consecutive nights
                time.sleep(2)
                sub_now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
                sub_params = params.copy()
                sub_params["mapId"] = int(sub_map_id)
                sub_params["seed"] = sub_now
                sub_params["bookingUid"] = str(uuid4())
                sub_resp = session.get(f"{BASE_URL}/api/availability/map", params=sub_params)
                session.headers["x-xsrf-token"] = get_latest_xsrf()
                if sub_resp.status_code != 200:
                    continue
                sub_avails = sub_resp.json().get("resourceAvailabilities", {})
                sub_sites = _check_consecutive_availability(sub_avails, config["nights"], start_date_str=config["start_date"])
                if sub_sites:
                    found_sites.extend(sub_sites)
                    break

        if found_sites:
            num_sites = len(found_sites)
            max_nights = max(s["consecutive_nights"] for s in found_sites)
            print(f"  ✅ {cg['name']}: AVAILABLE! ({num_sites} site(s), up to {max_nights} nights)")
            cg["available_sites"] = found_sites
            available_campgrounds.append(cg)
            # Return first match immediately so Playwright can launch ASAP
            # Remaining campgrounds will be checked on the next cycle
            return available_campgrounds
        else:
            print(f"  ❌ {cg['name']}: No availability")

    return available_campgrounds


# Map tent count to subEquipmentCategoryId
TENT_OPTIONS_IDS = {
    1: -32768,
    2: -32767,
    3: -32766,
}


def launch_playwright_add_to_cart(campground_name, config, gtc_email=None, gtc_password=None):
    """Launch Playwright to add a site to cart."""
    from playwright.sync_api import sync_playwright

    start_date = config["start_date"]
    end_date = config["end_date"]
    people = config["people"]
    tents = config["tents"]
    tent_label = TENT_OPTIONS.get(tents, "1 Tent")

    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    start_aria = start_dt.strftime("%B %-d, %Y")
    end_aria = end_dt.strftime("%B %-d, %Y")

    print(f"\n{'=' * 60}")
    print(f"  Launching Playwright to add to cart")
    print(f"  Campground: {campground_name}")
    print(f"  Dates: {start_date} to {end_date}")
    print(f"  People: {people}, Tents: {tents}")
    print(f"{'=' * 60}\n")

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
        except Exception:
            pass

        # Step 2: Login
        print("[2/6] Logging in...")
        page.get_by_role("button", name="Sign in to your account").click()
        page.wait_for_load_state("networkidle")
        time.sleep(1)
        page.get_by_role("textbox", name="Email").fill(gtc_email)
        page.get_by_role("textbox", name="Password").fill(gtc_password)
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
        page.get_by_role("combobox", name="Select park").fill(campground_name[:3].lower())
        time.sleep(1)
        page.get_by_role("option", name=campground_name).click()
        time.sleep(1)
        print(f"  ✅ Selected {campground_name}")

        # Step 4: Set dates and party size
        print("[4/6] Setting dates and party size...")
        try:
            date_area = page.locator('mat-date-range-input, [class*="date-range"]').first
            if date_area.is_visible(timeout=3000):
                date_area.click()
                time.sleep(1)
        except Exception:
            pass

        try:
            start_btn = page.locator(f'button[aria-label*="{start_aria}"]').first
            if start_btn.is_visible(timeout=3000):
                start_btn.click()
                time.sleep(0.5)
            end_btn = page.locator(f'button[aria-label*="{end_aria}"]').first
            if end_btn.is_visible(timeout=3000):
                end_btn.click()
                time.sleep(0.5)
            print(f"  ✅ Selected dates: {start_date} to {end_date}")
        except Exception as e:
            print(f"  ⚠️  Date issue: {e} - set manually")

        # People
        add_people_clicks = people - 2
        if add_people_clicks > 0:
            for _ in range(add_people_clicks):
                page.get_by_role("button", name="Add one").click()
                time.sleep(0.3)
            print(f"  ✅ Set party size to {people}")

        # Equipment
        try:
            page.locator("#equipment-field-wrapper > .mat-mdc-text-field-wrapper > .mat-mdc-form-field-flex").click()
            time.sleep(0.5)
            page.get_by_role("option", name=tent_label).click()
            time.sleep(0.5)
            print(f"  ✅ Selected equipment: {tent_label}")
        except Exception:
            pass

        # Step 5: Search
        print("[5/6] Searching for availability...")
        page.get_by_role("button", name="Search for availability").click()
        page.wait_for_load_state("networkidle")
        time.sleep(3)

        # Switch to list view
        page.get_by_role("radio", name="List view of results").click()
        time.sleep(2)
        print("  ✅ Switched to List view")

        # Click site group
        try:
            site_group = page.get_by_role("button", name=re.compile(r"Site.*")).first
            if site_group.is_visible(timeout=5000):
                site_group.click()
                time.sleep(2)
        except Exception:
            pass

        # Click first available site
        try:
            available_site = page.get_by_role("button", name=re.compile(r".*Available.*")).first
            if available_site.is_visible(timeout=5000):
                site_text = available_site.inner_text()
                available_site.click()
                time.sleep(2)
                print(f"  ✅ Selected: {site_text.strip()}")
        except Exception:
            print("  ⚠️  Select a site manually")

        # Step 6: Reserve
        print("[6/6] Adding to cart...")
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
                except Exception:
                    pass

                # Confirm
                try:
                    page.get_by_role("button", name="Confirm reservation details").click(timeout=10000)
                    time.sleep(3)
                    print("  ✅ Added to cart!")
                    send_telegram(
                        f"🏕 Site added to cart!\n"
                        f"📍 {campground_name}\n"
                        f"📅 {start_date} to {end_date}\n"
                        f"👥 {people} people, {tents} tent(s)\n"
                        f"🔗 {BASE_URL}/cart\n"
                        f"⏰ Go to VNC to checkout!"
                    )
                except Exception:
                    pass
        except Exception:
            send_telegram(
                f"🏕 Site found at {campground_name}!\n"
                f"📅 {start_date} to {end_date}\n"
                f"⏰ Connect to VNC to add to cart manually."
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


def main():
    parser = argparse.ArgumentParser(description="Campsite Watcher + Auto Add-to-Cart")
    parser.add_argument("--campground", help="Only watch a specific campground name")
    parser.add_argument("--user", default=DEFAULT_USER, help=f"User profile for GTC login (default: {DEFAULT_USER})")
    parser.add_argument("--dry-run", action="store_true", help="Check availability without adding to cart")
    parser.add_argument("--once", action="store_true", help="Check once and exit (don't loop)")
    args = parser.parse_args()

    gtc_email, gtc_password = get_user_credentials(args.user)
    if not gtc_email or not gtc_password:
        print(f"ERROR: No credentials found for user '{args.user}'")
        print(f"  Set GTC_{args.user}_EMAIL and GTC_{args.user}_PASSWORD in .env")
        sys.exit(1)

    config = load_config()

    print("=" * 60)
    print("  Campsite Watcher + Auto Add-to-Cart")
    print("=" * 60)
    print(f"  User: {args.user} ({gtc_email})")
    print(f"  Dates: {config['start_date']} to {config['end_date']}")
    print(f"  Nights: {config['nights']} consecutive")
    print(f"  People: {config['people']}, Tents: {config['tents']}")
    print(f"  Polling: every {config['polling_interval']} minutes")
    if args.campground:
        print(f"  Filter: {args.campground}")
    print(f"  GoingToCamp campgrounds: {len(config['campgrounds'])}")
    for cg in config["campgrounds"]:
        print(f"    • [GTC] {cg['name']}")
    print(f"  Recreation.gov campgrounds: {len(config['recdotgov_campgrounds'])}")
    for cg in config["recdotgov_campgrounds"]:
        print(f"    • [Rec] {cg['name']}")
    print("=" * 60)
    print()

    if args.dry_run:
        print("[DRY RUN] Checking availability once...\n")

    # Track active Playwright process (max 1 at a time)
    playwright_process = None
    playwright_campground = None  # which campground has the active browser

    check_count = 0
    while True:
        check_count += 1
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n[{now_str}] Check #{check_count}...")

        # Check if Playwright process has exited
        if playwright_process is not None:
            if playwright_process.poll() is not None:
                print(f"  ℹ️  Browser for {playwright_campground} closed (exit code {playwright_process.returncode})")
                playwright_process = None
                playwright_campground = None

        # Check GoingToCamp campgrounds
        available = []
        try:
            available = check_availability(config, campground_name=args.campground, gtc_email=gtc_email, gtc_password=gtc_password)
        except Exception as e:
            print(f"  ❌ Error checking GoingToCamp: {e}")

        # Also check Recreation.gov campgrounds
        try:
            recdotgov_available = check_recdotgov_availability(config, campground_name=args.campground)
            available.extend(recdotgov_available)
        except Exception as e:
            print(f"  ❌ Error checking Recreation.gov: {e}")

        if available:
            for cg in available:
                cg_name = cg["name"].replace(" State Park", "")
                short_name = CAMPGROUND_NAMES.get(cg["id"], cg_name)

                # Build details string from available sites info
                sites_info = cg.get("available_sites", [])
                num_sites = len(sites_info)
                max_nights = max((s["consecutive_nights"] for s in sites_info), default=config["nights"])

                # Get actual available dates from first site (best consecutive run)
                best_site = max(sites_info, key=lambda s: s["consecutive_nights"]) if sites_info else {}
                avail_start = best_site.get("avail_start", config["start_date"])
                avail_end = best_site.get("avail_end", config["end_date"])

                # List site IDs (show up to 5)
                site_ids = [str(s["resourceId"]) for s in sites_info[:5]]
                site_ids_str = ", ".join(site_ids)
                if num_sites > 5:
                    site_ids_str += f" (+{num_sites - 5} more)"

                details = (
                    f"📍 {cg['name']}\n"
                    f"📅 Available: {avail_start} to {avail_end} ({max_nights} night(s))\n"
                    f"🔍 Search window: {config['start_date']} to {config['end_date']}\n"
                    f"🏕 {num_sites} site(s): {site_ids_str}\n"
                    f"👥 {config['people']} people, {config['tents']} tent(s)"
                )

                print(f"\n🎉 AVAILABILITY FOUND: {cg['name']}! ({num_sites} sites, {avail_start} to {avail_end}, {max_nights} nights)")

                if cg.get("provider") == "RecreationDotGov":
                    # Recreation.gov — send Telegram with booking link only
                    booking_url = f"https://www.recreation.gov/camping/campgrounds/{cg['id']}"
                    print(f"  📱 Sending Telegram notification (Recreation.gov)")
                    send_telegram(
                        f"🏕 Campsite Available!\n"
                        f"{details}\n"
                        f"🔗 {booking_url}\n"
                        f"⏰ Book manually on Recreation.gov!"
                    )
                elif args.dry_run:
                    print("  [DRY RUN] Would launch Playwright to add to cart.")
                    send_telegram(
                        f"🏕 [DRY RUN] Availability found!\n"
                        f"{details}"
                    )
                else:
                    # GoingToCamp: launch Playwright if no browser is currently open
                    # Re-check if process has exited before deciding
                    if playwright_process is not None and playwright_process.poll() is not None:
                        print(f"  ℹ️  Previous browser closed (exit code {playwright_process.returncode})")
                        playwright_process = None
                        playwright_campground = None

                    if playwright_process is None:
                        print(f"  🚀 Launching browser for {cg['name']}...")
                        send_telegram(
                            f"🏕 Availability Found! Adding to cart...\n"
                            f"{details}\n"
                            f"⏰ Launching browser in VNC..."
                        )
                        # Spawn Playwright with actual available dates
                        playwright_process = subprocess.Popen(
                            [sys.executable, str(PROJECT_ROOT / "scripts" / "playwright_add_to_cart.py")],
                            env={
                                **os.environ,
                                "CAMPLY_CAMPGROUND": short_name,
                                "CAMPLY_START_DATE": avail_start,
                                "CAMPLY_END_DATE": avail_end,
                                "CAMPLY_PEOPLE": str(config["people"]),
                                "CAMPLY_TENTS": str(config["tents"]),
                                "GTC_EMAIL": gtc_email,
                                "GTC_PASSWORD": gtc_password,
                            },
                        )
                        playwright_campground = cg["name"]
                    else:
                        # Browser already open — just send notification
                        print(f"  📱 Browser already open for {playwright_campground}. Sending notification only.")
                        send_telegram(
                            f"🏕 Also Available!\n"
                            f"{details}\n"
                            f"ℹ️ Browser already open for {playwright_campground}.\n"
                            f"Close it to auto-book this one next."
                        )
        else:
            print("  No availability found.")

        if args.once or args.dry_run:
            break

        print(f"  Sleeping {config['polling_interval']} minutes...")
        time.sleep(config["polling_interval"] * 60)


if __name__ == "__main__":
    main()
