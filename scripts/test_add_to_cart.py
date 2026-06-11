#!/usr/bin/env python3
"""
GoingToCamp Add-to-Cart Test Script

Tests the full flow: login → get cart → find available site → add to cart.
Run individual steps with:
    python scripts/test_add_to_cart.py login        # Test login only
    python scripts/test_add_to_cart.py cart         # Test login + get cart
    python scripts/test_add_to_cart.py availability # Test finding available sites
    python scripts/test_add_to_cart.py add          # Full flow: find + add to cart
    python scripts/test_add_to_cart.py              # Same as 'add'

Requires .env with:
    GTC_EMAIL=your@email.com
    GTC_PASSWORD=yourpassword
    TELEGRAM_BOT_TOKEN=...
    TELEGRAM_CHAT_ID=...
"""

import json
import sys
import os
from pathlib import Path
from datetime import datetime
from uuid import uuid4

import requests
from dotenv import load_dotenv
from fake_useragent import UserAgent

# Load .env from project root
PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# --- Configuration ---
BASE_URL = "https://washington.goingtocamp.com"
GTC_EMAIL = os.getenv("GTC_EMAIL")
GTC_PASSWORD = os.getenv("GTC_PASSWORD")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Default search params (can be overridden via campgrounds.conf)
START_DATE = "2026-06-19"
END_DATE = "2026-06-21"
PEOPLE = 5
TENTS = 1

# Map tent count to subEquipmentCategoryId
TENT_MAP = {
    1: -32768,
    2: -32767,
    3: -32766,
}

# Test campground: Conconully State Park (has availability for test)
TEST_CAMPGROUND_ID = -2147483628
TEST_CAMPGROUND_NAME = "Conconully State Park"

APP_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "app-version": "5.110.184",
    "app-language": "en-US",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Expires": "0",
}


class GoingToCampClient:
    """Client for GoingToCamp API interactions."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": UserAgent(browsers=["chrome"]).random,
            **APP_HEADERS,
        })
        self.xsrf_token = None
        self.cart = None
        self.shopper_uid = None

    def login(self) -> bool:
        """Authenticate with GoingToCamp. Returns True on success."""
        print(f"[1/4] Logging in as {GTC_EMAIL}...")

        # Step 1: Initialize session - load home page + config/features to get cookies
        print("     Initializing session...")
        self.session.get(BASE_URL)
        self.session.post(
            f"{BASE_URL}/api/config/features",
            json=["AccountDeletion", "DirectResourceLocationMapAccess"],
        )

        # Extract XSRF token from cookies
        for cookie in self.session.cookies:
            if "xsrf" in cookie.name.lower():
                self.xsrf_token = cookie.value
                break

        if not self.xsrf_token:
            print("  ❌ Failed to get XSRF token from session init")
            return False

        # Set XSRF header for all subsequent requests
        self.session.headers["x-xsrf-token"] = self.xsrf_token

        # Step 2: Call login API
        resp = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": GTC_EMAIL, "password": GTC_PASSWORD},
        )

        if resp.status_code != 200:
            print(f"  ❌ Login failed: {resp.status_code} {resp.text}")
            return False

        # Update XSRF token from post-login cookies (may have rotated)
        for cookie in self.session.cookies:
            if "xsrf" in cookie.name.lower():
                self.xsrf_token = cookie.value
                self.session.headers["x-xsrf-token"] = self.xsrf_token
                break

        print(f"  ✅ Login successful")
        print(f"     XSRF token: {self.xsrf_token[:40]}...")
        return True

    def get_cart(self) -> bool:
        """Get or create cart session. Returns True on success."""
        print(f"[2/4] Getting cart session...")

        # Set XSRF header for subsequent requests
        if self.xsrf_token:
            self.session.headers["x-xsrf-token"] = self.xsrf_token

        resp = self.session.get(f"{BASE_URL}/api/cart")

        if resp.status_code != 200:
            print(f"  ❌ Get cart failed: {resp.status_code} {resp.text[:200]}")
            return False

        self.cart = resp.json()
        cart_uid = self.cart.get("cartUid")
        transaction_uid = self.cart.get("createTransactionUid")
        self.shopper_uid = self.cart.get("shopperUid") or self.cart.get("shopper", {}).get("shopperUid")

        print(f"  ✅ Cart retrieved")
        print(f"     cartUid: {cart_uid}")
        print(f"     transactionUid: {transaction_uid}")
        print(f"     shopperUid: {self.shopper_uid}")
        return True

    def find_available_site(self, campground_id: int, start_date: str, end_date: str) -> dict:
        """
        Find an available campsite at the given campground.
        Returns resource details dict or None.
        """
        print(f"[3/4] Searching for available sites at campground {campground_id}...")
        print(f"     Dates: {start_date} to {end_date}")

        # First we need the mapId for this campground
        maps_resp = self.session.get(f"{BASE_URL}/api/maps")
        if maps_resp.status_code != 200:
            print(f"  ❌ Failed to get maps: {maps_resp.status_code}")
            return None

        maps = maps_resp.json()
        map_id = None
        for m in maps:
            for link in m.get("mapLinks", []):
                if link.get("resourceLocationId") == campground_id:
                    map_id = link.get("childMapId")
                    break
            if map_id:
                break

        if not map_id:
            print(f"  ❌ Could not find mapId for campground {campground_id}")
            return None

        print(f"     mapId: {map_id}")

        # Build availability search params matching the real browser request
        now = datetime.utcnow().isoformat(timespec="milliseconds") + "Z"
        booking_uid = str(uuid4())
        self._last_booking_uid = booking_uid

        search_params = {
            "mapId": map_id,
            "bookingCategoryId": 0,
            "startDate": start_date,
            "endDate": end_date,
            "isReserving": "true",
            "getDailyAvailability": "false",
            "equipmentCategoryId": -32768,
            "subEquipmentCategoryId": TENT_MAP.get(TENTS, -32768),
            "numEquipment": 0,
            "boatLength": 0,
            "boatDraft": 0,
            "boatWidth": 0,
            "cartUid": self.cart.get("cartUid", ""),
            "cartTransactionUid": self.cart.get("createTransactionUid", ""),
            "bookingUid": booking_uid,
            "seed": now,
            "peopleCapacityCategoryCounts": json.dumps(
                [{"capacityCategoryId": -32767, "subCapacityCategoryId": None, "count": PEOPLE}]
            ),
            "filterData": json.dumps([
                {"attributeDefinitionId": -32759, "attributeDefinitionDecimalValue": 0, "enumValues": [1], "filterStrategy": 0, "attributeType": 0},
                {"attributeDefinitionId": -32708, "attributeDefinitionDecimalValue": 0, "enumValues": [1], "filterStrategy": 0, "attributeType": 0},
            ]),
        }

        avail_resp = self.session.get(
            f"{BASE_URL}/api/availability/map",
            params=search_params,
        )

        if avail_resp.status_code != 200:
            print(f"  ❌ Availability check failed: {avail_resp.status_code} {avail_resp.text[:200]}")
            return None

        avail_data = avail_resp.json()
        resource_availabilities = avail_data.get("resourceAvailabilities", {})

        # Find first available resource (availability value 0 = available)
        available_resources = []
        for resource_id_str, avail_info in resource_availabilities.items():
            availabilities = avail_info.get("availability", {})
            if any(v == 0 for v in availabilities.values()):
                available_resources.append({
                    "resourceId": int(resource_id_str),
                    "resourceLocationId": campground_id,
                    "mapId": map_id,
                })

        if not available_resources:
            print(f"  ⚠️  No available sites found for these dates")
            return None

        site = available_resources[0]
        print(f"  ✅ Found {len(available_resources)} available site(s)")
        print(f"     Using first: resourceId={site['resourceId']}")
        return site

    def add_to_cart(self, site: dict, start_date: str, end_date: str) -> bool:
        """
        Add a campsite to cart.
        site: dict with resourceId, resourceLocationId, mapId
        Returns True on success.
        """
        print(f"[4/4] Adding site {site['resourceId']} to cart...")

        booking_uid = str(uuid4())
        resource_blocker_uid = str(uuid4())
        now = datetime.utcnow().isoformat(timespec="milliseconds") + "Z"

        # Build the booking entry
        booking = {
            "bookingUid": booking_uid,
            "cartUid": self.cart["cartUid"],
            "bookingCategoryId": 0,
            "bookingModel": 0,
            "newVersion": {
                "cartTransactionUid": self.cart["createTransactionUid"],
                "bookingMembers": [],
                "bookingVehicles": [],
                "bookingBoats": [],
                "bookingCapacityCategoryCounts": [
                    {
                        "capacityCategoryId": -32767,
                        "subCapacityCategoryId": None,
                        "count": PEOPLE,
                    }
                ],
                "rateCategoryId": -32768,
                "resourceBlockerUids": [resource_blocker_uid],
                "resourceNonSpecificBlockerUids": [],
                "resourceZoneBlockerUids": [],
                "resourceZoneEntryBlockerUids": [],
                "startDate": start_date,
                "endDate": end_date,
                "releasePersonalInformation": False,
                "equipmentCategoryId": -32768,
                "subEquipmentCategoryId": TENT_MAP.get(TENTS, -32768),
                "occupant": {
                    "contact": {
                        "email": "",
                        "contactName": "",
                        "phoneNumberCountryCode": None,
                        "phoneNumber": "",
                    },
                    "address": {},
                    "allowMarketing": False,
                    "phoneNumbers": {},
                    "preferredCultureName": "en-US",
                    "firstName": self.cart.get("shopper", {}).get("currentVersion", {}).get("firstName", ""),
                    "lastName": self.cart.get("shopper", {}).get("currentVersion", {}).get("lastName", ""),
                },
                "requiresCheckout": False,
                "bookingStatus": 0,
                "completedDate": now,
                "arrivalComment": "",
                "entryPointResourceId": None,
                "exitPointResourceId": None,
                "bookingSurcharges": [],
                "consentToRelease": False,
                "equipmentDescription": "",
                "groupHoldUid": "",
                "organizationName": "",
                "passExpiryDate": None,
                "passNumber": "",
                "resourceLocationId": site["resourceLocationId"],
                "checkInTime": None,
                "checkOutTime": None,
                "deferredPayment": False,
            },
            "createTransactionUid": self.cart["createTransactionUid"],
            "currentVersion": None,
            "history": [],
            "drafts": [],
            "referenceNumberPostfix": "",
        }

        # Build resource blocker
        resource_blocker = {
            "blockerType": 0,
            "cartUid": self.cart["cartUid"],
            "resourceBlockerUid": resource_blocker_uid,
            "bookingUid": booking_uid,
            "groupHoldUid": "",
            "isReservation": True,
            "newVersion": {
                "creationDate": now,
                "cartTransactionUid": self.cart["createTransactionUid"],
                "startDate": start_date,
                "endDate": end_date,
                "resourceId": site["resourceId"],
                "resourceLocationId": site["resourceLocationId"],
                "status": 0,
            },
        }

        # Build the full cart commit payload
        commit_payload = {"cart": self.cart.copy()}
        commit_payload["cart"]["bookings"] = [booking]
        commit_payload["cart"]["resourceBlockers"] = [resource_blocker]

        # Update lastEditDate on newTransaction
        if commit_payload["cart"].get("newTransaction"):
            commit_payload["cart"]["newTransaction"]["lastEditDate"] = now

        resp = self.session.post(
            f"{BASE_URL}/api/cart/commit",
            params={"isCompleted": "false", "isSelfCheckIn": "false"},
            json=commit_payload,
        )

        if resp.status_code == 200:
            print(f"  ✅ Successfully added to cart!")
            print(f"     Response: {resp.text[:100]}")
            print(f"     Site {site['resourceId']} is now in your cart.")
            print(f"     Go to https://washington.goingtocamp.com/cart to checkout.")
            return True
        else:
            print(f"  ❌ Add to cart failed: {resp.status_code}")
            print(f"     Response: {resp.text[:500]}")
            return False

    def send_telegram(self, message: str):
        """Send a Telegram notification."""
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            print("  ⚠️  Telegram not configured, skipping notification")
            return

        resp = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": message},
        )
        if resp.status_code == 200:
            print(f"  📱 Telegram notification sent")
        else:
            print(f"  ⚠️  Telegram failed: {resp.status_code}")


def main():
    step = sys.argv[1] if len(sys.argv) > 1 else "add"

    if not GTC_EMAIL or not GTC_PASSWORD:
        print("ERROR: Set GTC_EMAIL and GTC_PASSWORD in .env")
        sys.exit(1)

    client = GoingToCampClient()

    # Step 1: Login
    if not client.login():
        sys.exit(1)
    if step == "login":
        print("\n✅ Login test passed!")
        return

    # Step 2: Get cart
    if not client.get_cart():
        sys.exit(1)
    if step == "cart":
        print("\n✅ Cart test passed!")
        return

    # Step 3: Find available site
    site = client.find_available_site(
        campground_id=TEST_CAMPGROUND_ID,
        start_date=START_DATE,
        end_date=END_DATE,
    )
    if step == "availability":
        if site:
            print("\n✅ Availability test passed!")
        else:
            print("\n⚠️  No sites available (not necessarily a failure)")
        return

    # Step 4: Add to cart
    if not site:
        print("\n⚠️  No available sites to add to cart. Try different dates.")
        sys.exit(1)

    if client.add_to_cart(site, START_DATE, END_DATE):
        client.send_telegram(
            f"🏕 Campsite added to cart!\n"
            f"📍 {TEST_CAMPGROUND_NAME}\n"
            f"📅 {START_DATE} to {END_DATE}\n"
            f"👥 {PEOPLE} people, {TENTS} tent(s)\n"
            f"🔗 https://washington.goingtocamp.com/cart"
        )
        print("\n✅ Full add-to-cart test passed!")
    else:
        print("\n❌ Add to cart failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
