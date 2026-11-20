import os
import sys

# Ensure root workspace and callcatch_ai are accessible in sys.path on Vercel
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(CURRENT_DIR)

if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from callcatch_ai.main import app

# Vercel Serverless Function entry point
# Exports 'app' for ASGI/WSGI gateway
