import os
import sys

# Ajouter le répertoire racine au PYTHONPATH pour Vercel Serverless
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

# Exposer l'application FastAPI pour Vercel
from app.main import app
