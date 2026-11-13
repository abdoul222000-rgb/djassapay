# ⚡ DjassaPay - SaaS E-commerce & Acompte Anti-Lapin

> **La solution n°1 en Afrique francophone (Côte d'Ivoire, Sénégal, Cameroun, Mali, etc.) pour les vendeurs sur WhatsApp, TikTok et Instagram.**
> Fini les livraisons impayées et les faux clients ("lapins") grâce à l'acompte obligatoire par **Wave** ou **Mobile Money (Orange Money, MTN MoMo, Moov)**.

---

## 🎯 Problème Résolu
À Abidjan, Dakar ou Douala, les commerçants expédient des commandes sans garantie. Dès que le coursier arrive à destination, le client ne décroche plus : le vendeur perd les frais de livraison de sa poche (1 500 à 2 500 FCFA).

**Avec DjassaPay :**
1. Le client passe commande sur la vitrine mobile ultra-rapide.
2. Pour valider l'expédition, le client règle **l'acompte Anti-Lapin** (frais de livraison ou acompte fixé) par **Wave** ou **Mobile Money**.
3. Dès que l'acompte est encaissé, la course est transmise au livreur à moto en 1 clic sur WhatsApp avec les coordonnées et le cash restant à récupérer.

---

## 🚀 Démarrer l'Application

### 1. Activer l'environnement virtuel Python
Dans le terminal PowerShell :
```powershell
.\venv\Scripts\Activate.ps1
```

### 2. Lancer le serveur
```powershell
python run.py
```
ou directement :
```powershell
.\venv\Scripts\python.exe run.py
```

L'application démarre sur : **`http://localhost:8000`**

---

## 🔗 Liens & Parcours de Démonstration

| Rôle | URL | Description |
| :--- | :--- | :--- |
| 🌐 **Accueil Plateforme** | `http://localhost:8000/` | Présentation générale du SaaS et accès rapides |
| ⚡ **Inscription Marchand** | `http://localhost:8000/register` | Création d'une nouvelle boutique en 30 secondes |
| 🔐 **Connexion Vendeur** | `http://localhost:8000/login` | Connexion rapide par WhatsApp + Code PIN |
| 🛒 **Vitrine Démo (Abidjan)** | `http://localhost:8000/shop/glamour-abidjan` | Boutique mode à Abidjan |
| 🛒 **Vitrine Démo (Dakar)** | `http://localhost:8000/shop/dakar-kicks` | Boutique sneakers à Dakar |
| 🏍️ **Hub des Coursiers** | `http://localhost:8000/delivery` | Liste de toutes les courses en attente |
| 📊 **Tableau de Bord Marchand**| `http://localhost:8000/merchant/dashboard` | Gestion des commandes et métriques |
| 👑 **Mon Abonnement SaaS** | `http://localhost:8000/merchant/subscription` | Passage au Plan Pro (6 750 FCFA / mois) |

---

## 🏗️ Architecture Technique
* **Backend :** Python 3.10+ avec **FastAPI** (asynchrone, haute performance)
* **Base de données :** SQLite (développement) / PostgreSQL (production) via SQLAlchemy ORM
* **Frontend :** HTML5 Mobile-first + Tailwind CSS + Alpine.js + Icônes Lucide
* **Intégration Paiement :**
  * Passerelle Wave Business (Direct API ou simulateur interactif)
  * CinetPay / Paystack pour Orange Money, MTN MoMo, Moov Money
* **Communication :** WhatsApp Cloud API & liens profonds `wa.me`

---

## 💰 Modèle de Monétisation
1. **Abonnement mensuel :** 6 750 FCFA / mois par boutique.
2. **Micro-commission :** 1% sur chaque acompte/transaction encaissé.
3. **Packs WhatsApp / SMS :** Notifications automatiques aux clients.
