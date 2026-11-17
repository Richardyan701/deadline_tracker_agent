"""Settings for every test.

Groot reads GROOT_MODEL from your own deadline_agent/.env when it starts.
An empty GROOT_MODEL set here wins over that file, so the tests always run
with the default model, whatever your own Groot is set to use.
"""

import os

os.environ["GROOT_MODEL"] = ""
