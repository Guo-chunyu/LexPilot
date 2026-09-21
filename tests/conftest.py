"""Keep the automated suite deterministic and prevent accidental live API calls."""

import os


os.environ["LEXPILOT_ENABLE_SEMANTIC_AI"] = "false"
# Existing unit tests exercise the deterministic domain engine without making
# real network calls. Production never sets this test-only compatibility flag.
os.environ["LEXPILOT_ALLOW_OFFLINE_FALLBACK"] = "true"
