import os
import re
import json
import time
from pathlib import Path

from dotenv import load_dotenv

from database import get_missions, update_analysis

# Chargement explicite du .env
ENV_PATH = Path(__file__).resolve().parent / ".env"
if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH, override=True)
else:
    load_dotenv(override=True)

MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")


def extract_json(content):
    if not content:
        raise ValueError("Réponse vide de Groq")
    content = content.strip()
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.IGNORECASE).strip()
    start = content.find("{")
    end = content.rfind("}") + 1
    if start == -1 or end <= start:
        raise ValueError("Aucun objet JSON trouvé")
    result = json.loads(content[start:end])
    if not isinstance(result, dict):
        raise ValueError("Le résultat JSON doit être un objet")
    return result


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
"""


def get_client():
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(f"GROQ_API_KEY absente du fichier .env ({ENV_PATH})")
    print("[AI] GROQ_API_KEY prefix:", api_key[:7], "| length:", len(api_key))
    from openai import OpenAI
    return OpenAI(api_key=api_key, base_url=BASE_URL)


def analyze_mission(mission, client=None, max_retries=6):
    if client is None:
        client = get_client()

    from openai import RateLimitError, APIError, APIConnectionError

    prompt = build_prompt(mission)
    attempt = 0
    wait = 2.0

    while True:
        try:
            response = client.chat.completions.create(
                model=MODEL,
                max_tokens=1500,
                temperature=0.1,
                messages=[{"role": "user", "content": prompt}]
            )
            break
        except RateLimitError as error:
            attempt += 1
            if attempt > max_retries:
                raise
            match = re.search(r"try again in ([\d.]+)(ms|s)", str(error))
            if match:
                value = float(match.group(1))
                wait = value / 1000.0 if match.group(2) == "ms" else value
                wait = max(wait, 1.0) + 1.0
            else:
                wait = min(wait * 2, 60.0)
            print(f"[AI RATE LIMIT] tentative {attempt}/{max_retries}, attente {wait:.1f}s")
            time.sleep(wait)
        except (APIConnectionError, APIError) as error:
            attempt += 1
            if attempt > max_retries:
                raise
            wait = min(wait * 2, 60.0)
            print(f"[AI API ERROR] tentative {attempt}/{max_retries}, attente {wait:.1f}s — {error}")
            time.sleep(wait)

    content = response.choices[0].message.content
    result = extract_json(content)

    try:
        score = int(result.get("score", 0))
    except (ValueError, TypeError):
        score = 0
    result["score"] = max(0, min(100, score))

    technologies = result.get("technologies", [])
    if isinstance(technologies, str):
        technologies = [technologies]
    if not isinstance(technologies, list):
        technologies = []
    result["technologies"] = technologies

    for field in ["experience", "location", "rate", "summary", "recommendation", "reason"]:
        result.setdefault(field, "Non précisé")

    return result


def analyze_all():
    missions = get_missions() or []
    if not missions:
        return {"status": "success", "total": 0, "analyzed": 0, "skipped": 0, "errors": 0, "message": "Aucune mission à analyser"}

    client = get_client()
    analyzed = 0
    skipped = 0
    errors = 0
    error_details = []

    print("\n" + "=" * 60)
    print("[AI] STARTING MISSION ANALYSIS (GROQ)")
    print("[AI] Total missions:", len(missions))
    print("[AI] Model:", MODEL)
    print("=" * 60)

    for index, mission in enumerate(missions, start=1):
        title = mission.get("title", "Unknown")
        url = mission.get("url")

        if mission.get("analysis"):
            skipped += 1
            continue
        if not url:
            errors += 1
            continue

        try:
            print(f"[AI {index}/{len(missions)}] Analyzing: {title}")
            result = analyze_mission(mission, client=client)
            update_analysis(url, result["score"], json.dumps(result, ensure_ascii=False))
            analyzed += 1
            print(f"[AI SUCCESS] {title} | Score: {result['score']}")
        except Exception as error:
            errors += 1
            error_details.append({"title": title, "url": url, "error": str(error)})
            print(f"[AI ERROR] {title}: {error}")

        # Pause anti-TPM (8K tokens/min sur le free tier)
        if index < len(missions):
            time.sleep(2.0)

    report = {
        "status": "completed",
        "total": len(missions),
        "analyzed": analyzed,
        "skipped": skipped,
        "errors": errors,
        "error_details": error_details[:20]
    }
    print("\n[AI] ANALYSIS FINISHED")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return report


if __name__ == "__main__":
    result = analyze_all()
    print(json.dumps(result, indent=2, ensure_ascii=False))