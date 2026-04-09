"""
Vercel ASGI entry point.
Vercel runs this file with /var/task as the working directory,
so we must explicitly add the api/ folder to sys.path before importing.
"""
import sys
from pathlib import Path

# Add this file's own directory (api/) to sys.path
sys.path.insert(0, str(Path(__file__).parent))

from main import app  # noqa: F401
