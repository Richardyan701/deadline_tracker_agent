#!/usr/bin/env bash
# Starts Agent Groot on Linux or macOS and opens it in your browser.
#
# Run it with:   ./start_groot.sh
# Press Ctrl+C to stop Groot.
cd "$(dirname "$0")"

URL="http://127.0.0.1:8000"

if [ ! -x .venv/bin/python ] || [ ! -f deadline_agent/.env ]; then
    echo "Groot is not set up yet, so please run ./setup.sh first."
    exit 1
fi

echo "Starting Groot. This can take a few seconds..."
# Started through Python, because some antivirus programs block the adk program itself
.venv/bin/python -m google.adk.cli web --port 8000 &
server=$!
# When this script ends (for example with Ctrl+C), stop the server too and wait until it has stopped
trap 'kill "$server" 2> /dev/null; wait "$server" 2> /dev/null' EXIT

# Ask the server once a second until it answers. Stop if it could not start.
until .venv/bin/python -c "import urllib.request as r; r.build_opener(r.ProxyHandler({})).open('$URL', timeout=1)" 2> /dev/null; do
    if ! kill -0 "$server" 2> /dev/null; then
        echo "Groot could not start. Read the messages above, or run: .venv/bin/python -m deadline_agent.check_setup"
        exit 1
    fi
    sleep 1
done

# Open it in the default browser: open on macOS, xdg-open on Linux
if [ "$(uname)" = "Darwin" ]; then
    open "$URL"
elif command -v xdg-open > /dev/null; then
    xdg-open "$URL" > /dev/null 2>&1 &
fi

echo
echo "Groot is running at $URL"
echo "Press Ctrl+C to stop it."
wait "$server"
