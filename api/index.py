"""Vercel serverless entrypoint for the Flask app.

Vercel runs this file as a Python serverless function and routes /api/*
to it (see vercel.json). The frontend is served statically from public/.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app  # noqa: E402,F401  (Vercel looks for `app`)
