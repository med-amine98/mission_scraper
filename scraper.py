"""
I-LEAD Mission Scraper (v8.0 - Ciblage CANDIDATS IT UNIQUEMENT)
Objectif : trouver les PROFILS de personnes IT qui CHERCHENT une opportunité
(ex: "à la recherche d'une nouvelle opportunité" + développeur)
PAS les offres d'emploi, PAS les recruteurs, PAS la fibre optique.
LinkedIn Candidats : via Google Dorking (Scavio).
"""
import csv
import json
import os
import random
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse, urldefrag, quote

import aiohttp
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

from database import save_mission, get_connection

load_dotenv(Path(__file__).resolve().parent / ".env")

# =====================================================
# CONFIGURATION GLOBALE
# =====================================================

BASE_DIR = Path(__file__).resolve().parent
SOURCES_FILE = BASE_DIR / "sources.json"
CSV_FILE = BASE_DIR / "missions.csv"

DEFAULT_TIMEOUT = 35000
DEFAULT_WAIT = 2000

MAX_LISTING_PAGES = 40
MAX_DETAILS_PER_SOURCE = 120
MAX_LINKEDIN_PAGES_PER_URL = 5

DELAY = 3.5
LINKEDIN_DELAY_MIN = 2.0
LINKEDIN_DELAY_MAX = 4.5

# =====================================================
# SCAVIO CONFIG
# =====================================================

SCAVIO_API_KEY = os.getenv("SCAVIO_API_KEY", "").strip()
SCAVIO_API_URL = "https://api.scavio.dev/api/v2/google"
LINKEDIN_CANDIDATES_MAX = int(os.getenv("LINKEDIN_CANDIDATES_MAX", "100"))

JOB_KEYWORDS = [
    "développeur", "developer", "data analyst", "data engineer", "data scientist",
    "python", "java", "javascript", "typescript", "react", "angular", "vue",
    "devops", "cloud", "aws", "azure", "gcp", "docker", "kubernetes",
    "cybersecurity", "cybersécurité", "consultant", "ingénieur", "ingenieur",
    "chef de projet", "business analyst", "architecte", "sap", "sql", "power bi",
    "machine learning", "intelligence artificielle", "infrastructure", "freelance",
    "mission", "product owner", "scrum master", "qa", "testeur", "fullstack", "backend",
]

# =====================================================
# FILTRE SOUS-TRAITANCE (jobs classiques)
# =====================================================

SUBCONTRACTING_SOURCES = {"hitechpros", "turnover_it", "littlebig"}

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

# =====================================================
# CIBLAGE CANDIDATS IT UNIQUEMENT
# =====================================================

CANDIDATE_INTENT_KEYWORDS = [
    # Français
    "à la recherche d'une nouvelle opportunité",
    "à la recherche d'un nouveau challenge",
    "à la recherche d'un poste",
    "je recherche un nouveau challenge",
    "je cherche une nouvelle opportunité",
    "je suis à la recherche",
    "en recherche d'emploi",
    "ouvert aux opportunités",
    "ouverte aux opportunités",
    "disponible immédiatement",
    "en reconversion",
    "je me présente",
    "mon parcours",
    "mon expertise",
    "n'hésitez pas à me contacter",
    "merci pour vos partages",
    # Anglais
    "looking for a new opportunity",
    "seeking new opportunities",
    "open to work",
    "open to opportunities",
    "actively looking",
    "available immediately",
    "my journey",
]

# ⚠️ UNIQUEMENT IT / TECH (fibre, télécoms, opérateurs supprimés)
SECTOR_KEYWORDS = [
    # Développement
    "développeur", "developer", "software engineer", "ingénieur logiciel",
    "frontend", "backend", "fullstack", "full-stack",
    "react", "angular", "vue", "node", "python", "java", "php",
    "typescript", "javascript", "c#", ".net", "golang", "rust",
    # Data / IA
    "data engineer", "data scientist", "data analyst",
    "machine learning", "intelligence artificielle", "ia",
    "big data", "spark", "hadoop", "kafka",
    # DevOps / Cloud
    "devops", "sre", "cloud", "aws", "azure", "gcp",
    "docker", "kubernetes", "terraform", "ci/cd",
    # Cybersécurité
    "cybersécurité", "cybersecurity", "sécurité informatique",
    "pentester", "soc analyst", "rssi",
    # IT général
    "it", "informatique", "systèmes", "réseau informatique",
    "architecte", "consultant it", "chef de projet it",
    "scrum master", "product owner", "qa", "testeur",
    "support it", "administrateur système",
]

CANDIDATE_EXCLUDE_KEYWORDS = [
    "nous recrutons", "we are hiring", "we're hiring",
    "offre d'emploi", "job offer", "poste à pourvoir",
    "envoyez votre cv", "send your cv", "postulez", "apply now",
    "cdi", "cdd", "stage", "alternance",
    "salaire", "rémunération", "package",
    "nous recherchons", "we are looking for",
]


def is_candidate_post(text: str) -> bool:
    """
    Filtre CANDIDAT IT :
    - 1 intention de candidat ET 1 mot-clé IT
    - OU au moins 2 mots-clés IT (post très orienté IT)
    - ET pas d'exclusion (recruteur)
    - Longueur min 50 caractères
    """
    text_lower = text.lower()

    # 1. Exclusion : recruteur ou offre d'emploi → rejet immédiat
    if any(k in text_lower for k in CANDIDATE_EXCLUDE_KEYWORDS):
        return False

    # 2. Longueur minimale
    if len(text) < 50:
        return False

    # 3. Compter les intentions de candidat et les mots-clés IT
    intent_count = sum(1 for k in CANDIDATE_INTENT_KEYWORDS if k in text_lower)
    sector_count = sum(1 for k in SECTOR_KEYWORDS if k in text_lower)

    # 4. Accepter si :
    if intent_count >= 1 and sector_count >= 1:
        return True
    if sector_count >= 2:
        return True

    return False


# =====================================================
# RECHERCHE LINKEDIN JOBS (inchangé)
# =====================================================

LINKEDIN_FRENCH_CITIES = [
    "Paris", "Lyon", "Marseille", "Toulouse", "Bordeaux",
    "Lille", "Nantes", "Strasbourg", "Nice", "Rennes",
    "Montpellier", "Grenoble",
]

LINKEDIN_SEARCH_QUERIES = [
    "sous-traitance informatique",
    "sous traitance IT",
    "mission freelance IT",
    "régie informatique",
    "prestation informatique",
    "mission ESN",
]

LINKEDIN_URLS = []
for city in LINKEDIN_FRENCH_CITIES:
    for query in LINKEDIN_SEARCH_QUERIES:
        encoded_query = quote(query)
        encoded_city = quote(city)
        LINKEDIN_URLS.append(
            f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
            f"?keywords={encoded_query}&location={encoded_city}&start=0"
        )

# =====================================================
# RECHERCHE LINKEDIN CANDIDATS (SCAVIO)
# =====================================================

LINKEDIN_CANDIDATES_SEARCH_TERMS = [
    # Développement
    "a la recherche d'une nouvelle opportunite developpeur",
    "a la recherche d'une nouvelle opportunite software engineer",
    "je recherche un nouveau challenge developpeur",
    "open to work developer",
    "looking for a new opportunity fullstack",
    # Data / IA
    "a la recherche d'une nouvelle opportunite data engineer",
    "a la recherche d'une nouvelle opportunite data scientist",
    "open to work data engineer",
    "looking for a new opportunity machine learning",
    # DevOps / Cloud
    "a la recherche d'une nouvelle opportunite devops",
    "open to work devops",
    "looking for a new opportunity cloud engineer",
    # Cybersécurité
    "a la recherche d'une nouvelle opportunite cybersecurite",
    "open to work cybersecurity",
    # IT général
    "a la recherche d'une nouvelle opportunite IT",
    "je recherche un nouveau challenge IT",
    "open to work IT",
]

# =====================================================
# CONFIGURATION DES SOURCES
# =====================================================

DEFAULT_SOURCES_CONFIG = {
    "turnover_it": {
        "enabled": True,
        "name": "Turnover-IT",
        "type": "standard",
        "urls": [
            "https://www.free-work.com/fr/tech-it/jobs?contracts=contractor",
            "https://www.free-work.com/fr/tech-it/jobs",
        ],
        "domains": ["free-work.com", "turnover-it.com"],
        "pattern": r"/fr/tech-it/jobs/(?!blog/|conseils/|aix-|clermont-|lyon-|paris-)[^/?]+",
    },
    "hitechpros": {
        "enabled": True,
        "name": "HiTechPros",
        "type": "standard",
        "urls": [
            "https://freelance.hitechpros.com/missions",
            "https://freelance.hitechpros.com/",
        ],
        "domains": ["hitechpros.com"],
        "pattern": r"/missions/\d+",
    },
    "littlebig_connection": {
        "enabled": True,
        "name": "LittleBig Connection",
        "type": "standard",
        "urls": [
            "https://app.littlebigconnection.com/fr/rfp/",
            "https://www.littlebigconnection.com/fr/prestataires/freelances",
        ],
        "domains": ["littlebigconnection.com"],
        "pattern": r"/fr/rfp/[^/?]+",
    },
    "linkedin": {
        "enabled": True,
        "name": "LinkedIn",
        "type": "linkedin_guest",
        "urls": LINKEDIN_URLS,
        "domains": ["linkedin.com"],
        "pattern": r"/jobs/view/\d+",
    },
    # linkedin_candidate géré séparément via Scavio
}


# =====================================================
# UTILITAIRES
# =====================================================

def clean_text(val):
    return re.sub(r"\s+", " ", val or "").strip()


def normalize_url(url):
    if not url:
        return ""
    url, _ = urldefrag(url)
    return url.rstrip("/")


def is_domain_allowed(url, domains):
    host = (urlparse(url).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in domains)


def is_listing_url(url):
    patterns = [
        r"/jobs/?$", r"/jobs/[a-z0-9_-]+/?$",
        r"/tech-it/jobs/?$", r"/tech-it/jobs/[a-z0-9_-]+/?$",
        r"/missions/?$", r"/rfp/?$", r"/prestataires/freelances/?$",
    ]
    return any(re.search(p, url, re.I) for p in patterns)


def looks_like_offer(title, content):
    text = (title + " " + content).lower()
    excluded = [
        "mot de passe oublié", "créer un compte", "connexion", "inscription",
        "politique de confidentialité", "mentions légales", "conditions générales",
    ]
    if any(x in text for x in excluded):
        return False
    return any(k in text for k in JOB_KEYWORDS) or len(title) >= 8


def is_likely_subcontracting(mission, source_key):
    title = str(mission.get("title") or "").lower()
    description = str(mission.get("description") or "").lower()
    text = f"{title} {description}"

    if any(marker in text for marker in SUBCONTRACTING_MARKERS):
        return True

    source_clean = source_key.lower().strip()
    if any(s in source_clean for s in SUBCONTRACTING_SOURCES):
        return True

    if "linkedin" in source_clean:
        return any(term in title for term in LINKEDIN_STRICT_TERMS)

    return False


# =====================================================
# EXTRACTION LINKEDIN JOBS (inchangé)
# =====================================================

def extract_linkedin_listing(html):
    offers = {}
    soup = BeautifulSoup(html, "html.parser")

    for card in soup.select("li"):
        try:
            urn_el = card.select_one("[data-entity-urn]")
            if not urn_el:
                continue
            urn = urn_el.get("data-entity-urn", "")
            id_match = re.search(r"jobPosting:(\d+)", urn)
            if not id_match:
                continue
            job_id = id_match.group(1)

            title_el = card.select_one("h3.base-search-card__title, .base-search-card__title")
            title = clean_text(title_el.get_text()) if title_el else ""

            company_el = card.select_one("h4.base-search-card__subtitle, .base-search-card__subtitle")
            company = clean_text(company_el.get_text()) if company_el else ""

            loc_el = card.select_one(".job-search-card__location")
            location = clean_text(loc_el.get_text()) if loc_el else ""

            link_el = card.select_one("a.base-card__full-link")
            url = link_el.get("href", "").split("?")[0] if link_el else f"https://www.linkedin.com/jobs/view/{job_id}"

            time_el = card.select_one("time")
            published = time_el.get("datetime", "") if time_el else ""

            if title and looks_like_offer(title, company + " " + location):
                offers[url] = {
                    "source": "linkedin",
                    "title": title, "company": company, "location": location,
                    "description": "", "skills": "", "rate": "",
                    "published_date": published, "url": url,
                }
        except Exception:
            continue

    return offers


def extract_linkedin_detail(page, mission):
    job_id_match = re.search(r"/jobs/view/(\d+)", mission["url"])
    if not job_id_match:
        return mission
    job_id = job_id_match.group(1)
    detail_url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"

    try:
        response = page.goto(detail_url, wait_until="domcontentloaded", timeout=30000)
        if not response or response.status >= 400:
            return mission

        page.wait_for_timeout(1500)
        soup = BeautifulSoup(page.content(), "html.parser")

        for sel in ["h2", "p"]:
            el = soup.select_one(sel)
            if el:
                t = clean_text(el.get_text())
                if t and 5 < len(t) < 200:
                    mission["title"] = t
                    break

        company_el = soup.select_one("a[href*='/company/']")
        if company_el:
            mission["company"] = clean_text(company_el.get_text())

        desc = ""
        for sel in ["[data-testid='expandable-text-box']", ".show-more-less-html__markup", ".description__text"]:
            el = soup.select_one(sel)
            if el:
                desc = clean_text(el.get_text("\n", strip=True))
                if len(desc) > 100:
                    break

        if desc:
            mission["description"] = desc[:15000]

        text = (mission.get("description", "") + " " + mission.get("title", "")).lower()
        skills = [k.capitalize() for k in JOB_KEYWORDS if re.search(r"(?<!\w)" + re.escape(k) + r"(?!\w)", text)]
        mission["skills"] = ", ".join(dict.fromkeys(skills))

    except Exception as exc:
        print("[LINKEDIN DETAIL ERROR]", mission["url"], exc)

    return mission


# =====================================================
# EXTRACTION GÉNÉRIQUE
# =====================================================

def extract_listing(soup, base_url, source, config):
    offers = {}
    pagination_links = set()
    pattern = config.get("pattern", "")
    domains = config.get("domains", [])

    for a in soup.select("a[href]"):
        raw_href = a.get("href", "")
        href = normalize_url(urljoin(base_url, raw_href))
        if not href or not is_domain_allowed(href, domains):
            continue
        if is_listing_url(href):
            continue

        if pattern and re.search(pattern, href, re.IGNORECASE):
            container = a
            for _ in range(5):
                parent = container.parent
                if not parent:
                    break
                container = parent
                tag = getattr(container, "name", "")
                classes = " ".join(container.get("class", [])).lower()
                if tag in ["article", "li", "tr"] or any(w in classes for w in ["card", "mission", "offer", "job", "result", "rfp"]):
                    break

            card_text = clean_text(container.get_text(" ", strip=True))
            heading = container.find(["h1", "h2", "h3", "h4"])
            title = clean_text(heading.get_text(" ", strip=True)) if heading else clean_text(a.get_text(" ", strip=True))

            if title.lower() in ["voir la mission", "voir cette offre", "en savoir plus", "postuler", "détails"]:
                title = ""
            if not title and len(card_text) > 20:
                title = card_text[:80]
            if not title or not looks_like_offer(title, card_text):
                continue

            location = ""
            for loc_elem in container.select("[class*='location'], [class*='localisation'], [class*='city']"):
                loc_txt = clean_text(loc_elem.get_text(" ", strip=True))
                if loc_txt and len(loc_txt) < 80:
                    location = loc_txt
                    break

            offers[href] = {
                "source": source, "title": title, "company": "", "location": location,
                "description": card_text[:8000], "skills": "", "rate": "",
                "published_date": "", "url": href,
            }
        elif "page=" in href or "/page/" in href or "pagination" in href.lower():
            pagination_links.add(href)

    return offers, pagination_links


def extract_detail(page, mission):
    if mission.get("source") == "linkedin":
        return extract_linkedin_detail(page, mission)

    try:
        response = page.goto(mission["url"], wait_until="domcontentloaded", timeout=DEFAULT_TIMEOUT)
        if not response or response.status >= 400:
            return mission

        page.wait_for_timeout(1000)
        soup = BeautifulSoup(page.content(), "html.parser")

        h1 = soup.find("h1")
        if h1:
            title = clean_text(h1.get_text(" ", strip=True))
            if title:
                mission["title"] = title

        for selector in ["main", "article", "[class*='description']", "[class*='detail']", "[class*='content']"]:
            element = soup.select_one(selector)
            if element:
                desc = clean_text(element.get_text(" ", strip=True))
                if len(desc) > len(mission.get("description", "")):
                    mission["description"] = desc[:15000]

        for meta in soup.select("meta"):
            prop = (meta.get("property") or meta.get("name") or "").lower()
            val = clean_text(meta.get("content", ""))
            if prop in ["article:published_time", "date"]:
                mission["published_date"] = val
            elif prop == "og:title" and not mission["title"]:
                mission["title"] = val

        text = ((mission.get("description") or "") + " " + (mission.get("title") or "")).lower()
        skills = [k.capitalize() for k in JOB_KEYWORDS if re.search(r"(?<!\w)" + re.escape(k) + r"(?!\w)", text)]
        mission["skills"] = ", ".join(dict.fromkeys(skills))

        if not mission.get("location"):
            for el in soup.select("[class*='location'], [class*='localisation'], [class*='place']"):
                loc = clean_text(el.get_text(" ", strip=True))
                if loc and len(loc) < 100:
                    mission["location"] = loc
                    break

        rate_match = re.search(r"(\d{3,4}\s*(?:€|EUR)\s*(?:/\s*j(?:our)?|TJM)?)", text, re.IGNORECASE)
        if rate_match:
            mission["rate"] = rate_match.group(0).strip()

    except Exception as exc:
        print(f"[DETAIL ERROR] {mission.get('url')}: {exc}")

    return mission


# =====================================================
# EXPORT CSV
# =====================================================

def export_to_csv():
    try:
        with get_connection() as conn:
            rows = conn.execute("""
                SELECT source, title, company, location,
                       description, skills, rate, published_date, url, collected_at
                FROM missions ORDER BY id DESC
            """).fetchall()

        columns = ["source", "title", "company", "location", "description",
                   "skills", "rate", "published_date", "url", "collected_at"]

        with open(CSV_FILE, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(columns)
            writer.writerows([[r[col] for col in columns] for r in rows])
    except Exception as e:
        print(f"[CSV EXPORT ERROR]: {e}")


# =====================================================
# SCRAPING LINKEDIN JOBS (Playwright)
# =====================================================

def _scrape_linkedin(browser, config: dict) -> int:
    source = "linkedin"
    context = browser.new_context(
        locale="fr-FR",
        viewport={"width": 1440, "height": 1000},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
    )
    page = context.new_page()
    page.set_default_timeout(DEFAULT_TIMEOUT)

    all_offers = {}
    visited_pages = set()
    saved_count = 0
    filtered_count = 0
    base_urls = list(config.get("urls", []))

    try:
        for base_idx, base_url in enumerate(base_urls, start=1):
            city_match = re.search(r"location=([^&]+)", base_url)
            query_match = re.search(r"keywords=([^&]+)", base_url)
            city = city_match.group(1) if city_match else "?"
            query = query_match.group(1) if query_match else "?"

            print(f"\n[LINKEDIN {base_idx}/{len(base_urls)}] {query} / {city}")

            for page_num in range(MAX_LINKEDIN_PAGES_PER_URL):
                start = page_num * 10
                current_url = re.sub(r"start=\d+", f"start={start}", base_url)

                if current_url in visited_pages:
                    continue
                visited_pages.add(current_url)

                try:
                    response = page.goto(current_url, wait_until="domcontentloaded", timeout=DEFAULT_TIMEOUT)
                    if not response:
                        break

                    status = response.status
                    if status == 429:
                        wait_s = min(15 * (2 ** min(page_num, 3)), 120)
                        print(f"[LINKEDIN 429] attente {wait_s}s...")
                        time.sleep(wait_s)
                        continue
                    if status >= 400:
                        print(f"[LINKEDIN HTTP {status}] {current_url}")
                        break

                    page.wait_for_timeout(1500)
                    html = page.content()

                    if len(html) < 3000:
                        print(f"[LINKEDIN] HTML trop court ({len(html)}), fin de cette URL")
                        break

                    found = extract_linkedin_listing(html)
                    new_count = 0
                    for url, mission in found.items():
                        if url not in all_offers:
                            all_offers[url] = mission
                            new_count += 1

                    print(f"  page {page_num + 1}/{MAX_LINKEDIN_PAGES_PER_URL} (start={start}) → {len(found)} trouvées, +{new_count} nouvelles")

                    for mission in list(found.values()):
                        if is_likely_subcontracting(mission, source):
                            try:
                                if save_mission(mission):
                                    saved_count += 1
                            except Exception as e:
                                print(f"  [SAVE ERROR] {e}")
                        else:
                            filtered_count += 1

                    if len(found) == 0:
                        break

                    time.sleep(random.uniform(LINKEDIN_DELAY_MIN, LINKEDIN_DELAY_MAX))

                except PlaywrightTimeout:
                    print(f"[LINKEDIN TIMEOUT] {current_url}")
                    break
                except Exception as e:
                    print(f"[LINKEDIN ERROR] {current_url}: {e}")
                    break

        print(f"\n[SCRAPER LINKEDIN] {len(all_offers)} offres uniques trouvées · "
              f"{saved_count} sauvegardées · {filtered_count} ignorées par le filtre")
        return len(all_offers)

    finally:
        context.close()


# =====================================================
# SCRAPING LINKEDIN CANDIDATS (SCAVIO - CIBLAGE IT UNIQUEMENT)
# =====================================================

def collect_linkedin_candidates_via_scavio() -> int:
    """
    Scrape les PROFILS de personnes IT qui CHERCHENT une opportunité.
    Utilise Scavio (Google Dorking).
    """
    if not SCAVIO_API_KEY:
        print("[LINKEDIN CANDIDATES] ❌ SCAVIO_API_KEY absent du .env")
        return 0

    print("\n[LINKEDIN CANDIDATES] Recherche de CANDIDATS IT...")
    all_candidates = []
    seen_urls = set()

    for term in LINKEDIN_CANDIDATES_SEARCH_TERMS:
        if len(all_candidates) >= LINKEDIN_CANDIDATES_MAX:
            print(f"[LINKEDIN CANDIDATES] Plafond {LINKEDIN_CANDIDATES_MAX} atteint, arrêt.")
            break

        print(f"[LINKEDIN CANDIDATES] Recherche '{term}'...")

        try:
            google_query = f"site:linkedin.com/posts {term}"
            
            response = requests.post(
                SCAVIO_API_URL,
                headers={"Authorization": f"Bearer {SCAVIO_API_KEY}"},
                json={"query": google_query},
                timeout=30,
            )

            if response.status_code != 200:
                print(f"[LINKEDIN CANDIDATES] HTTP {response.status_code} pour '{term}'")
                continue

            data = response.json()
            results = data.get("organic_results", [])
            print(f"[LINKEDIN CANDIDATES] '{term}' → {len(results)} résultats bruts")
            count = 0

            for result in results:
                post_url = result.get("link", "")
                snippet = result.get("snippet", "")
                title = result.get("title", "")

                if not post_url or post_url in seen_urls:
                    continue

                full_text = f"{title} {snippet}"

                # Filtre CANDIDAT IT
                if not is_candidate_post(full_text):
                    continue

                seen_urls.add(post_url)
                count += 1

                author_name = title.split(' sur LinkedIn')[0].split(' | LinkedIn')[0].strip()
                if not author_name or len(author_name) > 80:
                    author_name = "Candidat IT"

                candidate = {
                    "source": "linkedin_candidate",
                    "title": f"👤 {author_name} — {snippet[:120]}",
                    "company": author_name,
                    "location": "",
                    "description": snippet[:2000],
                    "skills": "",
                    "rate": "",
                    "published_date": "",
                    "url": post_url,
                }
                all_candidates.append(candidate)

                if len(all_candidates) >= LINKEDIN_CANDIDATES_MAX:
                    break

            print(f"[LINKEDIN CANDIDATES] '{term}' → +{count} (cumul {len(all_candidates)})")
            time.sleep(random.uniform(2.0, 4.0))

        except Exception as exc:
            print(f"[LINKEDIN CANDIDATES] Erreur Scavio '{term}': {exc}")

    # Sauvegarde
    saved_count = 0
    for candidate in all_candidates:
        try:
            if save_mission(candidate):
                saved_count += 1
        except Exception as e:
            print(f"[LINKEDIN CANDIDATES] Save error: {e}")

    print(f"[SCRAPER LINKEDIN CANDIDATES] {len(all_candidates)} candidats trouvés · "
          f"{saved_count} sauvegardés")
    return len(all_candidates)


# =====================================================
# SCRAPING GÉNÉRIQUE
# =====================================================

def _scrape_single_source(browser, source: str) -> int:
    config = DEFAULT_SOURCES_CONFIG.get(source)
    if not config:
        raise ValueError(f"Source non prise en charge : {source}")

    if config.get("type") == "linkedin_guest":
        return _scrape_linkedin(browser, config)

    print(f"\n[SCRAPER] Lancement du scraping pour {config.get('name', source)}...")
    context = browser.new_context(
        locale="fr-FR",
        viewport={"width": 1440, "height": 1000},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
    )
    page = context.new_page()
    page.set_default_timeout(DEFAULT_TIMEOUT)

    offers = {}
    queue = list(config.get("urls", []))
    visited = set()
    saved_count = 0
    filtered_count = 0

    try:
        while queue and len(visited) < MAX_LISTING_PAGES:
            current_url = normalize_url(queue.pop(0))
            if current_url in visited:
                continue
            visited.add(current_url)

            try:
                response = page.goto(current_url, wait_until="domcontentloaded", timeout=DEFAULT_TIMEOUT)
                if not response or response.status >= 400:
                    continue

                page.wait_for_timeout(DEFAULT_WAIT)
                soup = BeautifulSoup(page.content(), "html.parser")

                found, pagination = extract_listing(soup, current_url, source, config)
                offers.update(found)

                for plink in pagination:
                    if plink not in visited and plink not in queue:
                        queue.append(plink)

                time.sleep(DELAY)
            except PlaywrightTimeout:
                print(f"[TIMEOUT LISTING] {current_url}")
            except Exception as e:
                print(f"[LISTING ERROR] {current_url}: {e}")

        detail_page = context.new_page()
        for idx, mission in enumerate(list(offers.values())[:MAX_DETAILS_PER_SOURCE], start=1):
            enriched = extract_detail(detail_page, mission)

            if enriched.get("title"):
                if is_likely_subcontracting(enriched, source):
                    if save_mission(enriched):
                        saved_count += 1
                else:
                    filtered_count += 1
                    print(f"[FILTER] Ignorée : {enriched.get('title', '?')[:60]}")

            time.sleep(DELAY)
        detail_page.close()

    finally:
        context.close()

    print(f"[SCRAPER] Terminé pour {source} : {len(offers)} trouvées, "
          f"{saved_count} sauvegardées, {filtered_count} ignorées.")
    return len(offers)


# =====================================================
# SCRAPING MULTI-SOURCES
# =====================================================

def scrape_source(browser_or_source, source_name=None):
    if source_name is None:
        source = str(browser_or_source).lower().strip()

        if source == "linkedin_candidate":
            return collect_linkedin_candidates_via_scavio()

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                return _scrape_single_source(browser, source)
            finally:
                browser.close()
    else:
        browser = browser_or_source
        source = str(source_name).lower().strip()

        if source == "linkedin_candidate":
            return collect_linkedin_candidates_via_scavio()

        return _scrape_single_source(browser, source)


def scrape_all_sources():
    results = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            for source in DEFAULT_SOURCES_CONFIG:
                if not DEFAULT_SOURCES_CONFIG[source].get("enabled", True):
                    continue
                try:
                    count = _scrape_single_source(browser, source)
                    results[source] = {"status": "success", "offers_processed": count}
                except Exception as exc:
                    results[source] = {"status": "error", "offers_processed": 0, "message": str(exc)}
        finally:
            browser.close()

    # LinkedIn Candidats via Scavio
    try:
        candidates_count = collect_linkedin_candidates_via_scavio()
        results["linkedin_candidate"] = {"status": "success", "offers_processed": candidates_count}
    except Exception as exc:
        results["linkedin_candidate"] = {"status": "error", "offers_processed": 0, "message": str(exc)}

    export_to_csv()
    return results