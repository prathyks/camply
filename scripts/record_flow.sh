#!/bin/bash
# Record your browser interactions with Playwright codegen
# This will open a browser and generate Python code based on your actions.
#
# Usage (from VNC terminal):
#   cd ~/camply
#   bash scripts/record_flow.sh
#
# Navigate through the full flow:
#   1. Accept cookies
#   2. Login
#   3. Search for campground
#   4. Switch to List view
#   5. Click on an available site
#   6. Click "Add to Stay"
#
# The generated code will be saved to scripts/recorded_flow.py

cd "$(dirname "$0")/.."

~/.local/share/pipx/venvs/camply/bin/python -m playwright codegen \
    --target python \
    --output scripts/recorded_flow.py \
    "https://washington.goingtocamp.com"
