import uvicorn

if __name__ == "__main__":
    print("=" * 60)
    print("🚀 Démarrage de DjassaPay (FastAPI + Wave & Mobile Money)")
    print("📍 URL Plateforme : http://localhost:8000")
    print("🛒 Vitrine Client Démo : http://localhost:8000/shop/glamour-abidjan")
    print("📊 Tableau de Bord Marchand : http://localhost:8000/merchant/dashboard")
    print("=" * 60)
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
