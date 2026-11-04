#!/usr/bin/env bash
# Sets up Agent Groot on Linux or macOS.
#
# 1. Checks that Python is 3.10 or newer.
# 2. Creates a virtual environment in .venv.
# 3. Installs the packages in requirements.txt.
# 4. Saves your Gemini API key in deadline_agent/.env (hidden while you paste it).
#
# Run it with:   ./setup.sh
# To use a different Python, for example:   PYTHON=python3.12 ./setup.sh
set -e
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"
ENV_FILE="deadline_agent/.env"

echo "Step 1 of 4: checking Python..."
if ! command -v "$PYTHON" > /dev/null; then
    echo "Could not find $PYTHON. Install Python 3.10 or newer from python.org, then run this script again."
    exit 1
fi
"$PYTHON" --version
if ! "$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
    echo "This Python is older than 3.10. Install Python 3.10 or newer, then run this script again."
    echo "If you already have a newer one, point the script at it, for example: PYTHON=python3.12 ./setup.sh"
    exit 1
fi

echo
echo "Step 2 of 4: creating the virtual environment in .venv ..."
"$PYTHON" -m venv .venv

echo
echo "Step 3 of 4: installing Google ADK. This can take a few minutes..."
.venv/bin/python -m pip install -r requirements.txt

echo
echo "Step 4 of 4: saving your Gemini API key in $ENV_FILE"
# With no .env yet, go straight to asking for the key. Otherwise ask first, and keep it unless the answer is y.
replace="y"
if [ -e "$ENV_FILE" ]; then
    read -r -p "$ENV_FILE already exists. Replace it with a new key? (y/N) " replace
fi
if [ "$replace" = "y" ] || [ "$replace" = "Y" ]; then
    read -r -s -p "Paste your Gemini API key and press Enter (it will not show on screen): " key
    echo
    if [ -z "$key" ]; then
        echo "No key was entered, so nothing was saved. Run ./setup.sh again when you have your key."
        exit 1
    fi
    rm -f "$ENV_FILE"
    umask 077  # the new file can only be read by your user account
    printf 'GOOGLE_GENAI_USE_ENTERPRISE=0\nGOOGLE_API_KEY=%s\n' "$key" > "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    unset key
    echo "Saved. Only your user account can read $ENV_FILE."
else
    echo "Kept your existing $ENV_FILE."
fi

echo
echo "All done. To start Groot, run ./start_groot.sh from the project folder."
