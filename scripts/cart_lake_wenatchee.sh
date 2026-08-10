#!/usr/bin/env bash
# Full add-to-cart launcher: Lake Wenatchee
# Wed Aug 26 -> Thu Aug 27, 7 people, 2 tents
# Runs the complete automation: login, search, select site, add to cart.

cd "$(dirname "$0")/.."

export DISPLAY=:1
export CAMPLY_CAMPGROUND="Lake Wenatchee"
export CAMPLY_START_DATE="2026-08-26"
export CAMPLY_END_DATE="2026-08-27"
export CAMPLY_PEOPLE=7
export CAMPLY_TENTS=2

~/.local/share/pipx/venvs/camply/bin/python scripts/playwright_add_to_cart.py
