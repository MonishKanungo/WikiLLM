"""
Vercel ASGI entry point.
Adds the backend directory to sys.path so that local imports work,
then re-exports the FastAPI 'app' for Vercel to discover.
"""
import sys
import os
from pathlib import Path

# Make backend/ importable
backend_dir = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

from main import app  # noqa: F401 — Vercel needs to find 'app'
