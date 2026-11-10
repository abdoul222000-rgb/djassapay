import uvicorn

if __name__ == "__main__":
    print("\n=======================================================")
    print("🚀 Démarrage de CallCatch AI (SaaS Marché USA)...")
    print("📍 URL du Dashboard : http://localhost:8050/dashboard")
    print("=======================================================\n")
    uvicorn.run("callcatch_ai.main:app", host="127.0.0.1", port=8050, reload=True)
