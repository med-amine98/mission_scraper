#Mission Scraper & Matching CV Intelligence

Plateforme complète de **veille commerciale IT** et de **matching intelligent de CVs**. Elle permet de collecter automatiquement les missions IT depuis les trois plateformes majeures, de les visualiser sur une interface web moderne, et de faire matcher instantanément votre vivier de candidats (CVs PDF, Word, texte) avec les offres trouvées pour identifier le profil idéal.

---
## 🌟 Fonctionnalités Principales

### 1. Scraping multi-sources 
.
### 2. Dashboard & Visualisation des Offres
- Vue d'ensemble avec statistiques par source et volume d'offres en base.
- Filtres en temps réel : recherche textuelle multi-champs (intitulé, techno, lieu) et filtre par plateforme.
- Badges distincts par source.
- Fiches détaillées avec description complète et lien direct vers l'offre originale.

### 3. Gestion des CVs & Candidats (Nouvelle Page)
- **Import multi-fichiers par glisser-déposer** : support des formats **PDF**, **Word (.docx)**, **TXT**, **Markdown**.
- **Parser automatique d'entités** : extrait automatiquement le nom, les coordonnées (email, téléphone), le rôle/titre visé, les années d'expérience et les compétences techniques clés.
- **Ajout manuel / Copier-coller** : saisie rapide pour créer un profil candidat à la volée.
- Vivier de candidats persistant stocké dans SQLite (`missions.db`).

### 4. Moteur de Matching Intelligent (Trouver le candidat idéal)
- **Mode A : Trouver le CV idéal pour une offre sélectionnée** :
  - Choisissez n'importe quelle offre (ou cliquez sur " Trouver le CV idéal" directement dans le tableau des missions).
  - L'algorithme classe tous vos CVs du plus adapté au moins adapté avec une jauge de compatibilité (0 à 100%).
  - Met en évidence les **compétences validées** (✓ en vert) et les **compétences manquantes** (✗ en rouge/orange).
  - Fournit une synthèse commerciale et une recommandation immédiate.
- **Mode B : Trouver les offres idéales pour un profil** :
  - Sélectionnez un candidat de votre vivier.
  - Le système trouve et classe automatiquement les meilleures missions correspondant à son stack et son niveau d'expérience.
- **Mode C : Matrice de compatibilité globale** :
  - Vue transversale des meilleures opportunités candidat-mission ayant un score supérieur à 65%.

---

## 🚀 Démarrage Rapide

### 1. Prérequis
- Python 3.10+ (environnement virtuel `venv` inclus dans le projet)
- Node.js 18+ et npm

### 2. Lancer le Backend (FastAPI)
Dans un premier terminal :
```powershell
.\venv\Scripts\activate
python -m uvicorn main:app --reload --port 8000
```
L'API est accessible sur : `http://127.0.0.1:8000`  
Documentation interactive Swagger : `http://127.0.0.1:8000/docs`

### 3. Lancer le Frontend (Vite / React)
Dans un second terminal :
```powershell
cd frontend\frontend
npm run dev
```
L'interface s'ouvre sur : `http://localhost:5173`

---

## 📁 Architecture du Projet

```
ilead_mission_scraper/
│
├── main.py                  # API FastAPI (routes missions, scraping, CVs & matching)
├── database.py              # Couche SQLite unifiée (missions, candidats/CVs)
├── scraper.py               # Moteur de scraping Playwright + BeautifulSoup pour les 3 sites
├── cv_matcher.py            # Moteur NLP de parsing de CVs et de calcul de matching
├── analyzer.py              # Analyse approfondie par IA (optionnel via clé Claude)
├── sources.json             # Configuration des 3 plateformes
├── missions.db              # Base de données SQLite persistante
├── missions.csv             # Export CSV synchronisé des offres
│
└── frontend/
    └── frontend/            # Application React (Vite)
        ├── src/
        │   ├── App.jsx      # Interface complète (Dashboard, Missions, CVs, Matching)
        │   ├── App.css      # Styles modernes et adaptatifs
        │   └── api.js       # Client API communicant avec FastAPI
        ├── package.json
        └── vite.config.js
```


# Manuellement via deux terminaux

Terminal 1 (Backend FastAPI) :

powershell
.\venv\Scripts\activate
python -m uvicorn main:app --reload --port 8000

Terminal 2 (Frontend React Vite) :

powershell
cd frontend\frontend
npm run dev

L'interface est accessible sur http://localhost:5173 et l'API sur http://127.0.0.1:8000
