import logging
import os
from .app import create_app
from .runtime import initialize

logging.basicConfig(level=logging.INFO)
if os.getenv("EXECUTION_MODE", "local") == "local":
    initialize()
app = create_app()
