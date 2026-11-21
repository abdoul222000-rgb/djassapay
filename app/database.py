import os
import shutil
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.config import settings

db_url = settings.DATABASE_URL
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

# Compatibilité Vercel Serverless (Système de fichiers en lecture seule sauf /tmp)
if os.getenv("VERCEL") and (not db_url or db_url.startswith("sqlite")):
    tmp_db = "/tmp/djassapay.db"
    if not os.path.exists(tmp_db):
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        src_db = os.path.join(base_dir, "djassapay.db")
        if os.path.exists(src_db):
            try:
                shutil.copy2(src_db, tmp_db)
            except Exception as err:
                print(f"[Vercel DB Init] Copie de base vers /tmp: {err}")
    db_url = f"sqlite:///{tmp_db}"

try:
    connect_args = {"check_same_thread": False} if (not db_url or db_url.startswith("sqlite")) else {}
    engine = create_engine(db_url, connect_args=connect_args)
    with engine.connect() as conn:
        pass
except Exception as e:
    print(f"[Database Warning] Échec de connexion à la base configurée ({e}). Bascule automatique de sécurité vers SQLite.")
    fallback_url = "sqlite:////tmp/djassapay.db" if os.getenv("VERCEL") else "sqlite:///./djassapay.db"
    engine = create_engine(fallback_url, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
