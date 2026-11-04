"""Shared test setup: puts scripts/ on the path and keeps tests from touching the network."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / 'scripts'
os.environ.setdefault('NOSEWORK_SKIP_DNS', '1')
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
