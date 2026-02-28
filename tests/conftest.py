import os
import sys

# Make `api/` importable from anywhere pytest is run
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))
