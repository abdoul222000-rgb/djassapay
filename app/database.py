from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.config import settings

# Normalisation URL PostgreSQL (Render utilise souvent postgres:// au lieu de postgresql://)
db_url = settings.DATABASE_URL
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

try:
    connect_args = {"check_same_thread": False} if db_url.startswith("sqlite") else {}
    engine = create_engine(db_url, connect_args=connect_args)
    # Test de connectivité immédiat
    with engine.connect() as conn:
        pass
except Exception as e:
    print(f"[Database Warning] Échec de connexion à la base configurée ({e}). Bascule automatique de sécurité vers SQLite.")
    engine = create_engine("sqlite:///./djassapay.db", connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
