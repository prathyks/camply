#!/usr/bin/env bash
# Search-only launcher: Lake Wenatchee
# Wed Aug 26 -> Thu Aug 27, 7 people, 2 tents
# Logs in + searches, then hands off to you to pick a site and add to cart.

cd "$(dirname "$0")/.."

export DISPLAY=:1
export CAMPLY_CAMPGROUND="Lake Wenatchee"
export CAMPLY_START_DATE="2026-08-26"
export CAMPLY_END_DATE="2026-08-27"
export CAMPLY_PEOPLE=7
export CAMPLY_TENTS=2

~/.local/share/pipx/venvs/camply/bin/python scripts/playwright_search_only.py
