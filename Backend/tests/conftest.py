# Backend/tests/conftest.py
"""Makes ``Backend.*`` absolute imports resolve when pytest is run from
anywhere, by putting the Account_Payables project root (the parent of
``Backend/``) on ``sys.path`` — the same root every application module
already imports relative to (e.g. ``Backend.API_Layer...``).
"""
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
