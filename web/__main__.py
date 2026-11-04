"""Start Agent Groot's web app with:  python -m web

On Windows, run it from the project folder with:  .venv\\Scripts\\python.exe -m web

One server serves both the chat (ADK's dev UI at /dev-ui/) and Groot's own
pages (at /groot). It only listens on 127.0.0.1, so other computers on your
network cannot open it. Press Ctrl+C to stop it.
"""

import logging

import uvicorn

from .app import HOST, PORT, build_app


def main() -> None:
    # Show the same INFO lines as `adk web`, like each request Groot sends to Gemini
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(build_app(), host=HOST, port=PORT)


if __name__ == "__main__":
    main()
