# Vercel serverless entry - imports your existing main.py Flask app
import os
import sys
# Add parent dir to path so we can import main.py
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from main import app

# Vercel expects 'app' variable
# Disable background thread on Vercel (serverless doesn't support it)
os.environ["VERCEL"] = "1"
