import re
from io import BytesIO
from typing import List, Optional
from contextlib import asynccontextmanager

import pandas as pd
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from database import (
    init_db,
    get_missions,
    get_mission,
    save_mission,
    save_cv,
    get_cvs,
    get_cv,
    delete_cv,
    delete_all_cvs,
    delete_all_missions,
    delete_mission_by_url,
)
from scraper import scrape_source, scrape_all_sources
from analyzer import analyze_all
from cv_matcher import (
    extract_text_from_bytes,
    parse_cv_profile,
    compute_match_score,
    extract_mission_skills,
)

# ============================================================
# CONFIGURATION
# ============================================================

APP_NAME = "I-Lead Mission Scraper & Matching Intelligence"
APP_VERSION = "4.0"   # ← Ciblage CANDIDATS IT (plus d'offres d'emploi)

ALLOWED_SOURCES = {
    "turnover_it",
    "hitechpros",
    "littlebig_connection",
    "linkedin",        # LinkedIn Jobs (API guest)
    "linkedin_candidate",  # LinkedIn Candidats (Scavio) — remplace linkedin_post
}

MAX_CSV_SIZE_BYTES = 10 * 1024 * 1024
MAX_CV_SIZE_BYTES = 5 * 1024 * 1024

# ============================================================
# FILTRE SOUS-TRAITANCE (pour les jobs classiques)
# ============================================================

SUBCONTRACTING_SOURCES = {
    "hitechpros",
    "turnover_it",
    "littlebig",
}

SUBCONTRACTING_MARKERS = [
    "sous-traitance", "sous traitant", "sous-traitant",
    "portage salarial", "portage", "sub-contracting", "subcontracting",
    "en sous-traitance", "mission sous-traitée",
    "prestation de sous-traitance",
    "assistance technique", "mode de facturation",
    "régie", "forfait",
    "intercontrat", "inter-contrat",
    "co-traitance", "co-traitant",
    "mission entre esn", "partenariat esn", "partenaire esn",
    "renfort d'équipe", "renfort technique", "renfort projet",
    "renfort de delivery",
    "mission freelance", "freelance / indépendant",
    "mission ouverte aux indépendants",
    "recherche prestataire", "besoin consultant",
    "apporteur d'affaires", "apport d'affaires",
    "business developer freelance",
    "mission en sous-traitance", "mission en régie",
    "recherche partenaire", "partenariat commercial",
    "mission portage",
    "offre ouverte aux esn",
    "consultant indépendant",
]

_MARKER_PATTERNS = [
    re.compile(
        r"(?<![a-zàâäéèêëîïôöùûüç])" + re.escape(m) + r"(?![a-zàâäéèêëîïôöùûüç])",
        re.IGNORECASE,
    )
    for m in SUBCONTRACTING_MARKERS
]

# ⚠️ FILTRE STRICT LINKEDIN JOBS
LINKEDIN_STRICT_TERMS = [
    "sous-trait", "sous trait",
    "freelance",
    "régie", "regie",
    "portage",
    "prestataire", "prestation",
    "partenariat esn", "partenaire esn",
    "renfort",
    "intercontrat", "inter-contrat",
    "co-traitance",
    "appel d'offres", "appel d’offres",
    "rfp",
]


def is_likely_subcontracting(mission: dict, source_key: str) -> bool:
    """
    Filtre pour les JOBS classiques.
    Les CANDIDATS (linkedin_candidate) ne passent PAS par ce filtre.
    """
    title = str(mission.get("title") or "").lower()
    description = str(mission.get("description") or "").lower()
    text = f"{title} {description}"

    for pattern in _MARKER_PATTERNS:
        if pattern.search(text):
            return True

    source_clean = source_key.lower().strip()
    if any(s in source_clean for s in SUBCONTRACTING_SOURCES):
        return True

    if "linkedin" in source_clean:
        return any(term in title for term in LINKEDIN_STRICT_TERMS)

    return False


def clean_non_subcontracting_from_db(source_key: str) -> int:
    """Ne nettoie pas les candidats (déjà filtrés à la source)."""
    if "linkedin_candidate" in source_key.lower():
        return 0

    try:
        all_missions = get_missions() or []
        to_delete = []

        for m in all_missions:
            m_source = str(m.get("source") or "").lower()
            if source_key.lower() not in m_source:
                continue
            if not is_likely_subcontracting(m, source_key):
                to_delete.append(m)

        deleted = 0
        if to_delete:
            print(f"[FILTER] {len(to_delete)} missions non-sous-traitance à supprimer")
            for m in to_delete:
                url = m.get("url")
                if url:
                    try:
                        delete_mission_by_url(url)
                        deleted += 1
                    except Exception as exc:
                        print(f"[FILTER] Impossible de supprimer {url}: {exc}")

        return deleted
    except Exception as exc:
        print(f"[FILTER] Erreur nettoyage base: {exc}")
        return 0


def no_cache(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"


class CandidateCreate(BaseModel):
    name: str
    title: Optional[str] = "Consultant IT"
    email: Optional[str] = ""
    phone: Optional[str] = ""
    experience_years: Optional[int] = 0
    skills: Optional[str] = ""
    summary: Optional[str] = ""
    raw_text: Optional[str] = ""


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        init_db()
        print("=" * 65)
        print(f"{APP_NAME} v{APP_VERSION} initialisé")
        print("Base de données connectée (missions.db)")
        print("Sources supportées :", ", ".join(sorted(ALLOWED_SOURCES)))
        print("Sources natives sous-traitance :", ", ".join(sorted(SUBCONTRACTING_SOURCES)))
        print("LinkedIn Jobs : filtre STRICT (termes explicites uniquement)")
        print("LinkedIn Candidats : filtre is_candidate_post (IT uniquement)")
        print("=" * 65)
        yield
    finally:
        print(f"{APP_NAME} arrêt en cours...")


app = FastAPI(
    title=APP_NAME,
    description="Plateforme de collecte de CANDIDATS IT et matching intelligent de CVs",
    version=APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# ROUTES SYSTÈME
# ============================================================

@app.get("/")
def home():
    return {"project": APP_NAME, "version": APP_VERSION, "status": "running"}


@app.get("/health")
def health():
    return {"status": "healthy", "backend": "online", "database": "initialized"}


@app.get("/info")
def info():
    return {
        "application": APP_NAME,
        "version": APP_VERSION,
        "sources": sorted(ALLOWED_SOURCES),
        "subcontracting_sources": sorted(SUBCONTRACTING_SOURCES),
        "total_missions": len(get_missions()),
        "total_candidates": len(get_cvs()),
    }


@app.get("/api/status")
def api_status():
    return {
        "api": "online",
        "application": APP_NAME,
        "version": APP_VERSION,
        "mode": "candidate-hunting-it",
    }


# ============================================================
# ROUTES MISSIONS
# ============================================================

@app.get("/missions")
def list_missions(response: Response):
    try:
        data = get_missions() or []
        no_cache(response)
        print(f"[API] GET /missions → {len(data)} missions")
        return data
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Database error: {str(error)}")


@app.delete("/missions")
def clear_all_missions(confirm: bool = Query(False, description="Confirmation obligatoire")):
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Suppression destructive : ajoutez ?confirm=true pour confirmer.",
        )
    try:
        count = delete_all_missions()
        print(f"[API] DELETE /missions → {count} supprimées")
        return {
            "status": "success",
            "deleted_count": count,
            "message": "Toutes les offres ont été supprimées.",
        }
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Erreur de suppression : {str(error)}")


@app.get("/missions/stats")
def mission_stats(response: Response):
    try:
        data = get_missions() or []
        source_stats = {s: 0 for s in ALLOWED_SOURCES}
        source_stats["autres"] = 0

        for m in data:
            src = str(m.get("source") or "").lower()
            matched = False
            for s in sorted(ALLOWED_SOURCES, key=len, reverse=True):
                if s in src:
                    source_stats[s] += 1
                    matched = True
                    break
            if not matched:
                source_stats["autres"] += 1

        cvs_count = len(get_cvs())
        no_cache(response)

        return {
            "total_missions": len(data),
            "total_candidates": cvs_count,
            "sources": source_stats,
            "mode": "candidate-hunting-it",
        }
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Stats error: {str(error)}")


@app.get("/missions/{mission_id}")
def get_single_mission(mission_id: int, response: Response):
    m = get_mission(mission_id)
    if not m:
        raise HTTPException(status_code=404, detail="Mission introuvable")
    no_cache(response)
    return m


# ============================================================
# ROUTES SCRAPING
# ============================================================

@app.post("/scrape/all")
def trigger_scrape_all():
    try:
        results = scrape_all_sources()
        total = sum(r.get("offers_processed", 0) for r in results.values())

        filtered_stats = {}
        total_removed = 0
        for source_key in sorted(ALLOWED_SOURCES):
            removed = clean_non_subcontracting_from_db(source_key)
            filtered_stats[source_key] = {"removed": removed}
            total_removed += removed

        total_in_db = len(get_missions() or [])
        print(
            f"[API] Scraping global terminé → {total} traitées, "
            f"{total_removed} supprimées, {total_in_db} en base"
        )

        return {
            "status": "completed",
            "total_processed": total,
            "total_removed_by_filter": total_removed,
            "total_in_db": total_in_db,
            "results": results,
            "filter_stats": filtered_stats,
        }
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Erreur de scraping global : {str(error)}")


@app.post("/scrape/{source}")
def trigger_scrape_source(source: str):
    source_clean = source.lower().strip()
    if source_clean not in ALLOWED_SOURCES:
        raise HTTPException(
            status_code=404,
            detail={
                "message": f"Source inconnue : {source_clean}",
                "available_sources": sorted(ALLOWED_SOURCES),
            },
        )
    try:
        count = scrape_source(source_clean)
        removed = clean_non_subcontracting_from_db(source_clean)
        total_in_db = len(get_missions() or [])

        print(
            f"[API] Scraping {source_clean} terminé → {count} traitées, "
            f"{removed} supprimées, {total_in_db} en base"
        )

        return {
            "source": source_clean,
            "offers_processed": count,
            "removed_by_filter": removed,
            "total_in_db": total_in_db,
            "status": "success",
            "mode": "candidate-hunting-it",
            "message": f"{count} éléments traités depuis {source_clean} ({removed} ignorés)",
        }
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Erreur de scraping ({source_clean}) : {str(error)}")


# ============================================================
# IMPORT CSV
# ============================================================

@app.post("/import/csv")
async def import_csv(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Veuillez fournir un fichier CSV valide.")

    try:
        content = await file.read()

        if len(content) > MAX_CSV_SIZE_BYTES:
            raise HTTPException(status_code=413, detail="Fichier CSV trop volumineux (max 10 Mo).")

        df = pd.read_csv(
            BytesIO(content),
            dtype=str,
            encoding="utf-8-sig",
            encoding_errors="replace",
            keep_default_na=False,
            sep=None,
            engine="python",
        )
        df.columns = [str(c).strip().lower() for c in df.columns]

        required = ["title", "url"]
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise HTTPException(status_code=400, detail=f"Colonnes obligatoires manquantes : {missing}")

        imported = 0
        skipped_filter = 0
        for _, row in df.iterrows():
            title = str(row.get("title", "")).strip()
            url = str(row.get("url", "")).strip()
            if not title or not url:
                continue

            mission_data = {
                "source": str(row.get("source", "CSV") or "CSV").strip(),
                "title": title,
                "company": str(row.get("company", "")).strip(),
                "description": str(row.get("description", "")).strip(),
                "location": str(row.get("location", "")).strip(),
                "skills": str(row.get("skills", "")).strip(),
                "rate": str(row.get("rate", "")).strip(),
                "published_date": str(row.get("published_date", "")).strip(),
                "url": url,
            }

            source_key = mission_data["source"].lower()
            if "linkedin_candidate" not in source_key:
                if not is_likely_subcontracting(mission_data, source_key):
                    skipped_filter += 1
                    continue

            save_mission(mission_data)
            imported += 1

        return {
            "status": "success",
            "imported": imported,
            "skipped_by_filter": skipped_filter,
            "message": f"{imported} éléments importés ({skipped_filter} ignorés).",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur d'import : {str(e)}")
    finally:
        await file.close()


# ============================================================
# ANALYSE IA
# ============================================================

@app.post("/analyze")
def trigger_analysis(force: bool = Query(False, description="Forcer la ré-analyse des offres déjà enrichies")):
    try:
        try:
            res = analyze_all(force=force)
        except TypeError:
            if force:
                raise HTTPException(
                    status_code=501,
                    detail="analyze_all() ne supporte pas encore force=true. Mettez à jour analyzer.py.",
                )
            res = analyze_all()

        message = "Analyse IA terminée"
        if not force and isinstance(res, dict) and res.get("analyzed") == 0 and res.get("skipped", 0) > 0:
            message = (
                f"Aucune offre analysée : {res.get('skipped')} déjà analysées ou filtrées. "
                f"Relancez avec ?force=true pour forcer la ré-analyse."
            )

        return {"status": "success", "message": message, "result": res}
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Analysis error: {str(error)}")


# ============================================================
# ROUTES CVs
# ============================================================

@app.get("/api/cvs")
def list_candidates(response: Response):
    try:
        data = get_cvs()
        no_cache(response)
        print(f"[API] GET /api/cvs → {len(data)} candidats")
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur de récupération des CVs : {str(e)}")


@app.post("/api/cvs")
def create_candidate(candidate: CandidateCreate):
    try:
        if not candidate.skills and candidate.raw_text:
            parsed = parse_cv_profile(candidate.raw_text, candidate.name)
            candidate.skills = parsed.get("skills", "")
            if not candidate.experience_years:
                candidate.experience_years = parsed.get("experience_years", 0)

        cv_dict = candidate.dict()
        cv_id = save_cv(cv_dict)
        return {
            "status": "success",
            "cv_id": cv_id,
            "message": f"Candidat {candidate.name} ajouté.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur d'ajout candidat : {str(e)}")


@app.post("/api/cvs/upload")
async def upload_cv_files(files: List[UploadFile] = File(...)):
    saved_candidates = []
    errors = []

    for file in files:
        try:
            content = await file.read()
            if len(content) > MAX_CV_SIZE_BYTES:
                errors.append(f"Fichier {file.filename} : trop volumineux (>5 Mo)")
                continue

            raw_text = extract_text_from_bytes(content, file.filename or "")
            if not raw_text or len(raw_text.strip()) < 10:
                errors.append(f"Fichier {file.filename} : aucun texte extractible")
                continue

            profile = parse_cv_profile(raw_text, file.filename or "")
            cv_id = save_cv(profile)
            profile["id"] = cv_id
            saved_candidates.append(profile)
        except Exception as exc:
            errors.append(f"Fichier {file.filename} : {str(exc)}")
        finally:
            await file.close()

    status = "success" if not errors else ("partial" if saved_candidates else "error")
    return {
        "status": status,
        "uploaded_count": len(saved_candidates),
        "candidates": saved_candidates,
        "errors": errors,
    }


@app.get("/api/cvs/{cv_id}")
def get_single_candidate(cv_id: int, response: Response):
    cv = get_cv(cv_id)
    if not cv:
        raise HTTPException(status_code=404, detail="CV introuvable")
    no_cache(response)
    return cv


@app.delete("/api/cvs")
def clear_all_candidates(confirm: bool = Query(False)):
    if not confirm:
        raise HTTPException(status_code=400, detail="Ajoutez ?confirm=true pour confirmer la suppression.")
    try:
        count = delete_all_cvs()
        return {"status": "success", "deleted_count": count, "message": "Tous les CVs ont été supprimés."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur de suppression globale : {str(e)}")


@app.delete("/api/cvs/{cv_id}")
def remove_candidate(cv_id: int):
    success = delete_cv(cv_id)
    if not success:
        raise HTTPException(status_code=404, detail="Candidat introuvable")
    return {"status": "success", "message": "CV supprimé avec succès"}


# ============================================================
# MATCHING
# ============================================================

@app.get("/api/match/mission/{mission_id}")
def match_cvs_for_mission(mission_id: int, response: Response):
    mission = get_mission(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission introuvable")

    candidates = get_cvs()
    no_cache(response)

    if not candidates:
        return {"mission": mission, "matches": [], "message": "Aucun CV enregistré."}

    scored_candidates = []
    for candidate in candidates:
        match_info = compute_match_score(candidate, mission)
        scored_candidates.append({"candidate": candidate, "match": match_info})

    scored_candidates.sort(key=lambda x: x["match"]["score"], reverse=True)
    best_match = scored_candidates[0] if scored_candidates else None

    return {
        "mission": mission,
        "total_evaluated": len(candidates),
        "best_match": best_match,
        "matches": scored_candidates,
    }


@app.get("/api/match/cv/{cv_id}")
def match_missions_for_cv(
    cv_id: int,
    response: Response,
    limit: int = Query(20, ge=1, le=200),
):
    candidate = get_cv(cv_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="CV introuvable")

    missions = get_missions()
    no_cache(response)

    if not missions:
        return {"candidate": candidate, "matches": [], "message": "Aucune mission en base."}

    scored_missions = []
    for mission in missions:
        match_info = compute_match_score(candidate, mission)
        scored_missions.append({"mission": mission, "match": match_info})

    scored_missions.sort(key=lambda x: x["match"]["score"], reverse=True)

    return {
        "candidate": candidate,
        "total_evaluated": len(missions),
        "matches": scored_missions[:limit],
    }


@app.get("/api/match/overview")
def matching_overview(response: Response):
    candidates = get_cvs()
    missions = get_missions()
    no_cache(response)

    if not candidates or not missions:
        return {
            "top_pairings": [],
            "total_candidates": len(candidates),
            "total_missions": len(missions),
            "message": "Données insuffisantes.",
        }

    all_pairs = []
    for c in candidates:
        for m in missions:
            res = compute_match_score(c, m)
            if res["score"] >= 65:
                all_pairs.append({
                    "candidate_id": c["id"],
                    "candidate_name": c["name"],
                    "candidate_title": c["title"],
                    "mission_id": m["id"],
                    "mission_title": m["title"],
                    "source": m.get("source"),
                    "score": res["score"],
                    "verdict": res["verdict"],
                    "matched_skills": res["matched_skills"],
                    "url": m.get("url"),
                })

    all_pairs.sort(key=lambda x: x["score"], reverse=True)

    return {
        "total_candidates": len(candidates),
        "total_missions": len(missions),
        "matches_count": len(all_pairs),
        "top_pairings": all_pairs[:30],
    }