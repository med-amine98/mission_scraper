import os
import re
import json
import time
from pathlib import Path

from dotenv import load_dotenv

from database import get_missions, update_analysis


# ============================================================
# CHARGEMENT EXPLICITE DU .ENV
# ============================================================

ENV_PATH = Path(__file__).resolve().parent / ".env"

if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH, override=True)
else:
    load_dotenv(override=True)

# Configuration Groq
MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")


# ============================================================
# CORRECTION 1 : DÉTECTION DES PAGES DE LISTING
# ============================================================

LISTING_URL_PATTERNS = [
    r"/jobs/?$",                      # /jobs
    r"/jobs/[a-z0-9_-]+/?$",          # /jobs/villeurbanne
    r"/tech-it/jobs/?$",              # /tech-it/jobs
    r"/tech-it/jobs/[a-z0-9_-]+/?$",  # /tech-it/jobs/villeurbanne
    r"/missions/?$",                  # /missions
    r"/rfp/?$",                       # /rfp
]

LISTING_TITLE_PATTERNS = [
    r"^trouvez votre prochaine",
    r"^recherche d.offres",
    r"^toutes les offres",
    r"^liste des (?:offres|missions)",
    r"^offres? d.emploi à",
]


def is_listing_page(mission):
    """
    Détecte une page de listing/navigation (pas une vraie mission).
    Ces pages ne doivent PAS être analysées par le LLM.
    """
    url = (mission.get("url") or "").lower()
    title = (mission.get("title") or "").lower()

    for pat in LISTING_URL_PATTERNS:
        if re.search(pat, url):
            return True

    for pat in LISTING_TITLE_PATTERNS:
        if re.search(pat, title):
            return True

    # Description vide ou trop courte = suspect
    desc = (mission.get("description") or "").strip()
    if len(desc) < 80:
        return True

    return False


# ============================================================
# CORRECTION 2 : JSON UTILITIES ROBUSTE
# ============================================================

def extract_json(content):
    """
    Extrait et valide un objet JSON depuis une réponse LLM.

    Robuste aux :
    - Fences markdown (```json ... ```)
    - Texte avant/après le JSON
    - Virgules finales (trailing commas)
    - Objets JSON multiples (prend le premier valide)
    """
    if not content:
        raise ValueError("Réponse vide de Groq")

    content = content.strip()

    # Étape 1 : retirer les fences markdown
    content = re.sub(
        r"^```(?:json)?\s*|\s*```$",
        "",
        content,
        flags=re.IGNORECASE
    ).strip()

    # Étape 2 : décodage incrémental
    # On essaie chaque "{" comme point de départ possible
    decoder = json.JSONDecoder()
    errors = []

    for start_match in re.finditer(r"\{", content):
        start = start_match.start()
        try:
            result, _end = decoder.raw_decode(content[start:])
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError as exc:
            errors.append(str(exc))
            continue

    # Étape 3 : fallback — nettoyer les virgules finales et réessayer
    cleaned = re.sub(r",\s*([}\]])", r"\1", content)
    start = cleaned.find("{")
    end = cleaned.rfind("}") + 1
    if start != -1 and end > start:
        try:
            result = json.loads(cleaned[start:end])
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError as exc:
            errors.append(str(exc))

    # Aucun JSON valide
    first_error = errors[0] if errors else "inconnue"
    preview = content[:200].replace("\n", " ")
    raise ValueError(
        f"Aucun objet JSON valide trouvé. "
        f"Première erreur : {first_error}. "
        f"Début de la réponse : {preview!r}"
    )


# ============================================================
# CORRECTION 3 : PROMPT RENFORCÉ
# ============================================================

def build_prompt(mission):

    return f"""
Tu es un expert senior en recrutement IT et en missions freelance.

Analyse la mission suivante pour une société de conseil informatique.

INFORMATIONS :

Titre : {mission.get('title', '')}
Entreprise : {mission.get('company', '')}
Description : {mission.get('description', '')}
Localisation : {mission.get('location', '')}
Compétences : {mission.get('skills', '')}
TJM : {mission.get('rate', '')}
Date de publication : {mission.get('published_date', '')}

OBJECTIFS :

1. Identifier les technologies et compétences demandées.
2. Estimer le niveau d'expérience requis.
3. Identifier la localisation et le mode de travail si disponibles.
4. Identifier le TJM uniquement s'il est mentionné.
5. Résumer clairement la mission.
6. Évaluer sa pertinence pour une société de conseil IT.
7. Donner une recommandation commerciale.

IMPORTANT :

- Ne jamais inventer un TJM.
- Ne jamais inventer une entreprise.
- Distinguer les informations explicites des estimations.
- Si une information est absente, indiquer "Non précisé".
- Le score doit être compris entre 0 et 100.
- Répondre uniquement avec un JSON valide.

FORMAT STRICT :

{{
    "score": 85,
    "technologies": ["Python", "FastAPI"],
    "experience": "Senior",
    "location": "Paris",
    "rate": "Non précisé",
    "summary": "Résumé de la mission",
    "recommendation": "Prioritaire",
    "reason": "Justification du score"
}}

RAPPEL FINAL : ta réponse doit être UNIQUEMENT un objet JSON.
- Pas de texte avant.
- Pas de texte après.
- Pas de ```json.
- Pas de commentaire.
- Pas de virgule finale.
Premier caractère = {{     Dernier caractère = }}
"""


# ============================================================
# CLIENT FACTORY
# ============================================================

def get_client():
    """Create and return an OpenAI-compatible client for Groq."""

    api_key = os.getenv("GROQ_API_KEY")

    if not api_key:
        raise RuntimeError(
            f"GROQ_API_KEY absente du fichier .env ({ENV_PATH})"
        )

    print(f"[AI] GROQ_API_KEY détectée (longueur: {len(api_key)})")

    from openai import OpenAI

    return OpenAI(
        api_key=api_key,
        base_url=BASE_URL
    )


# ============================================================
# SINGLE MISSION ANALYSIS
# ============================================================

def analyze_mission(mission, client=None, max_retries=6):
    """
    Analyse une mission via Groq.
    Réessaie automatiquement en cas de 429 (rate limit / TPM)
    avec un backoff exponentiel.
    """

    if client is None:
        client = get_client()

    from openai import RateLimitError, APIError, APIConnectionError

    prompt = build_prompt(mission)
    attempt = 0
    wait = 2.0
    response = None

    while True:
        try:
            response = client.chat.completions.create(
                model=MODEL,
                max_tokens=1500,
                temperature=0.1,
                response_format={"type": "json_object"},   # ← JSON garanti
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )
            break

        except RateLimitError as error:
            attempt += 1
            if attempt > max_retries:
                raise

            match = re.search(
                r"try again in ([\d.]+)(ms|s)",
                str(error)
            )
            if match:
                value = float(match.group(1))
                wait = value / 1000.0 if match.group(2) == "ms" else value
                wait = max(wait, 1.0) + 1.0
            else:
                wait = min(wait * 2, 60.0)

            print(
                f"[AI RATE LIMIT] tentative {attempt}/{max_retries}, "
                f"attente {wait:.1f}s"
            )
            time.sleep(wait)

        except (APIConnectionError, APIError) as error:
            attempt += 1
            if attempt > max_retries:
                raise

            wait = min(wait * 2, 60.0)
            print(
                f"[AI API ERROR] tentative {attempt}/{max_retries}, "
                f"attente {wait:.1f}s — {error}"
            )
            time.sleep(wait)

    if response is None:
        raise RuntimeError("Aucune réponse obtenue après les tentatives")

    content = response.choices[0].message.content

    result = extract_json(content)

    # Normalize score
    try:
        score = int(result.get("score", 0))
    except (ValueError, TypeError):
        score = 0
    result["score"] = max(0, min(100, score))

    # Normalize list
    technologies = result.get("technologies", [])
    if isinstance(technologies, str):
        technologies = [technologies]
    if not isinstance(technologies, list):
        technologies = []
    result["technologies"] = technologies

    # Ensure required fields
    for field in [
        "experience",
        "location",
        "rate",
        "summary",
        "recommendation",
        "reason"
    ]:
        result.setdefault(field, "Non précisé")

    return result


# ============================================================
# ANALYZE ALL MISSIONS
# ============================================================

def analyze_all(force: bool = False):
    """
    Analyse toutes les missions via Groq.

    Args:
        force (bool): si True, ré-analyse même les missions déjà analysées.
                      Utilisé par /analyze?force=true
    """

    missions = get_missions() or []

    if not missions:
        return {
            "status": "success",
            "total": 0,
            "analyzed": 0,
            "skipped": 0,
            "errors": 0,
            "force": force,
            "message": "Aucune mission à analyser"
        }

    client = get_client()

    analyzed = 0
    skipped = 0
    errors = 0
    error_details = []
    skipped_details = []

    print("\n" + "=" * 60)
    print("[AI] STARTING MISSION ANALYSIS (GROQ)")
    print("[AI] Total missions:", len(missions))
    print("[AI] Model:", MODEL)
    print("[AI] Base URL:", BASE_URL)
    print("[AI] Force:", force)
    print("=" * 60)

    for index, mission in enumerate(missions, start=1):

        title = mission.get("title", "Unknown")
        url = mission.get("url")

        # ✅ CORRECTION 1 : skip les pages de listing
        if is_listing_page(mission):
            skipped += 1
            skipped_details.append({
                "title": title,
                "url": url,
                "reason": "page de listing (pas une mission)"
            })
            print(f"[AI SKIP {index}/{len(missions)}] {title} → page de listing")
            continue

        # Skip missions déjà analysées (sauf force)
        if mission.get("analysis") and not force:
            skipped += 1
            skipped_details.append({
                "title": title,
                "url": url,
                "reason": "déjà analysée"
            })
            continue

        if not url:
            errors += 1
            error_details.append({
                "title": title,
                "url": None,
                "error": "URL manquante"
            })
            continue

        try:
            print(f"[AI {index}/{len(missions)}] Analyzing: {title}")

            result = analyze_mission(
                mission,
                client=client
            )

            update_analysis(
                url,
                result["score"],
                json.dumps(result, ensure_ascii=False)
            )

            analyzed += 1

            print(
                f"[AI SUCCESS] {title} | "
                f"Score: {result['score']}"
            )

        except Exception as error:

            errors += 1

            error_details.append({
                "title": title,
                "url": url,
                "error": str(error)
            })

            print(f"[AI ERROR] {title}: {error}")

        # Pause anti-TPM (8 000 tokens/min sur le free tier)
        if index < len(missions):
            time.sleep(2.0)

    report = {
        "status": "completed",
        "total": len(missions),
        "analyzed": analyzed,
        "skipped": skipped,
        "errors": errors,
        "force": force,
        "error_details": error_details[:20],
        "skipped_details": skipped_details[:20]
    }

    print("\n[AI] ANALYSIS FINISHED")
    print(json.dumps(report, indent=2, ensure_ascii=False))

    return report


# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Analyse IA des missions via Groq"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Forcer la ré-analyse des missions déjà enrichies"
    )
    args = parser.parse_args()

    result = analyze_all(force=args.force)
    print(json.dumps(result, indent=2, ensure_ascii=False))