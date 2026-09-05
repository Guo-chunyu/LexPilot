"""Keep the automated suite deterministic and prevent accidental live API calls."""

import os


os.environ["LEXPILOT_ENABLE_SEMANTIC_AI"] = "false"
