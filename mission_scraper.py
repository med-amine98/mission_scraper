
import csv
import re
import sqlite3
import time
from datetime import datetime
from urllib.parse import urljoin, urlparse, urldefrag

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout


# =====================================================
# CONFIGURATION
# =====================================================

SOURCES = {
    "turnover_it": {
        "urls": [
            "https://www.free-work.com/fr/tech-it/jobs?contracts=contractor",
            "https://www.free-work.com/fr/tech-it/jobs"
        ],
        "domains": ["free-work.com"],
        "pattern": r"/fr/tech-it/jobs/[^/?]+"
    },
    "hitechpros": {
        "urls": [
            "https://freelance.hitechpros.com/missions",
            "https://freelance.hitechpros.com/"
        ],
        "domains": ["hitechpros.com"],
        "pattern": r"/missions/\d+"
    },
    "littlebig_connection": {
        "urls": [
            "https://app.littlebigconnection.com/fr/rfp/",
            "https://www.littlebigconnection.com/fr/prestataires/freelances"
        ],
        "domains": ["littlebigconnection.com"],
        "pattern": r"/fr/rfp/[^/?]+"
    }
}

DB_FILE = "missions.db"
CSV_FILE = "missions.csv"

MAX_LISTING_PAGES = 8
MAX_DETAILS = 100
DELAY = 1.5

JOB_KEYWORDS = [
    "développeur", "developer", "data analyst",
    "data engineer", "data scientist", "python",
    "java", "javascript", "react", "angular",
    "devops", "cloud", "aws", "azure",
    "cybersecurity", "cybersécurité",
    "consultant", "ingénieur", "ingenieur",
    "chef de projet", "business analyst",
    "architecte", "sap", "sql", "power bi",
    "machine learning", "intelligence artificielle",
    "technicien", "administrateur", "réseau",
    "infrastructure", "freelance", "mission",
    "product owner", "scrum master", "qa",
    "testeur", "mlo ps"
]


# =====================================================
# DATABASE
# =====================================================

def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS missions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT,
                title TEXT,
                company TEXT,
                location TEXT,
                description TEXT,
                skills TEXT,
                published_date TEXT,
                url TEXT UNIQUE,
                collected_at TEXT
            )
        """)


def save_mission(m):
    if not m.get("url") or not m.get("title"):
        return False

    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.execute("""
            INSERT INTO missions (
                source, title, company, location,
                description, skills, published_date,
                url, collected_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)

            ON CONFLICT(url) DO UPDATE SET
                title = excluded.title,
                description = CASE
                    WHEN length(excluded.description) >
                         length(missions.description)
                    THEN excluded.description
                    ELSE missions.description END,
                company = CASE
                    WHEN excluded.company != ''
                    THEN excluded.company
                    ELSE missions.company END,
                location = CASE
                    WHEN excluded.location != ''
                    THEN excluded.location
                    ELSE missions.location END,
                skills = CASE
                    WHEN excluded.skills != ''
                    THEN excluded.skills
                    ELSE missions.skills END
        """, (
            m["source"], m["title"], m["company"],
            m["location"], m["description"],
            m["skills"], m["published_date"],
            m["url"], datetime.now().isoformat()
        ))

        return cursor.rowcount > 0


# =====================================================
# HELPERS
# =====================================================

def clean(value):
    return re.sub(r"\s+", " ", value or "").strip()


def normalize(url):
    if not url:
        return ""

    url, _ = urldefrag(url)
    return url.rstrip("/")


def allowed_domain(url, domains):
    host = (urlparse(url).hostname or "").lower()

    return any(
        host == d or host.endswith("." + d)
        for d in domains
    )


def is_valid_offer_url(url, pattern):
    return bool(re.search(pattern, url, re.I))


def looks_like_offer(title, content):
    text = (title + " " + content).lower()

    # Eviter les pages de connexion et d'inscription.
    excluded = [
        "mot de passe oublié",
        "créer un compte",
        "connexion",
        "inscription",
        "politique de confidentialité"
    ]

    if any(x in text for x in excluded):
        return False

    return (
        any(k in text for k in JOB_KEYWORDS)
        or len(title) >= 15
    )


# =====================================================
# HTML EXTRACTION
# =====================================================

def extract_listing(soup, base_url, source, config):

    offers = {}
    listing_links = set()

    pattern = config["pattern"]
    domains = config["domains"]

    for a in soup.select("a[href]"):

        href = normalize(urljoin(
            base_url,
            a.get("href", "")
        ))

        if not href:
            continue

        if not allowed_domain(href, domains):
            continue

        # Détecter les annonces individuelles.
        if is_valid_offer_url(href, pattern):

            container = a

            # Chercher la carte qui contient l'annonce.
            for _ in range(6):
                parent = container.parent

                if not parent:
                    break

                container = parent

                tag = getattr(container, "name", "")

                classes = " ".join(
                    container.get("class", [])
                ).lower()

                if (
                    tag in ["article", "li"]
                    or any(
                        word in classes
                        for word in [
                            "card", "mission", "offer",
                            "job", "result", "rfp"
                        ]
                    )
                ):
                    break

            card_text = clean(
                container.get_text(" ", strip=True)
            )

            heading = container.find(
                ["h1", "h2", "h3", "h4"]
            )

            title = (
                clean(heading.get_text(" ", strip=True))
                if heading
                else clean(a.get_text(" ", strip=True))
            )

            if title.lower() in [
                "voir la mission",
                "voir cette offre",
                "en savoir plus"
            ]:
                title = ""

            if not title:
                continue

            if not looks_like_offer(title, card_text):
                continue

            offers[href] = {
                "source": source,
                "title": title,
                "company": "",
                "location": "",
                "description": card_text[:10000],
                "skills": "",
                "published_date": "",
                "url": href
            }

        # Détecter les pages de pagination.
        elif (
            "page=" in href
            or "pagination" in href.lower()
        ):
            listing_links.add(href)

    return offers, listing_links


# =====================================================
# DETAIL EXTRACTION
# =====================================================

def extract_detail(page, mission):

    try:
        response = page.goto(
            mission["url"],
            wait_until="domcontentloaded",
            timeout=30000
        )

        if not response or response.status >= 400:
            print("[DETAIL HTTP]", mission["url"])
            return mission

        page.wait_for_timeout(1000)

        html = page.content()
        soup = BeautifulSoup(html, "html.parser")

        # Titre
        h1 = soup.find("h1")

        if h1:
            title = clean(h1.get_text(" ", strip=True))

            if title:
                mission["title"] = title

        # Description
        for selector in [
            "main",
            "article",
            "[class*='description']",
            "[class*='detail']",
            "[class*='content']"
        ]:
            element = soup.select_one(selector)

            if element:
                description = clean(
                    element.get_text(" ", strip=True)
                )

                if len(description) > len(
                    mission["description"]
                ):
                    mission["description"] = description[:15000]

        # Métadonnées
        for meta in soup.select("meta"):
            prop = (
                meta.get("property")
                or meta.get("name")
                or ""
            ).lower()

            value = clean(meta.get("content", ""))

            if prop == "article:published_time":
                mission["published_date"] = value

            if prop == "og:title" and not mission["title"]:
                mission["title"] = value

        # Extraction de compétences
        text = mission["description"].lower()

        skills = [
            keyword for keyword in JOB_KEYWORDS
            if keyword in text
        ]

        mission["skills"] = ", ".join(
            dict.fromkeys(skills)
        )

        # Extraction de localisation basique.
        for element in soup.select(
            "[class*='location'], [class*='localisation']"
        ):
            location = clean(element.get_text(" ", strip=True))

            if location and len(location) < 150:
                mission["location"] = location
                break

    except Exception as exc:
        print("[DETAIL ERROR]", mission["url"], exc)

    return mission


# =====================================================
# SCRAPING SOURCE
# =====================================================

def scrape_source(browser, source):

    config = SOURCES[source]

    print("\n" + "=" * 65)
    print("[START]", source)
    print("=" * 65)

    context = browser.new_context(
        locale="fr-FR",
        viewport={"width": 1440, "height": 1000},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"
        )
    )

    page = context.new_page()

    offers = {}
    queue = list(config["urls"])
    visited = set()

    try:
        while queue and len(visited) < MAX_LISTING_PAGES:

            current = normalize(queue.pop(0))

            if current in visited:
                continue

            visited.add(current)

            print("[LISTING]", current)

            try:
                response = page.goto(
                    current,
                    wait_until="domcontentloaded",
                    timeout=45000
                )

                if not response:
                    print("[NO RESPONSE]", current)
                    continue

                print("[HTTP]", response.status)

                if response.status >= 400:
                    continue

                page.wait_for_timeout(2500)

                html = page.content()
                soup = BeautifulSoup(html, "html.parser")

                found, pagination = extract_listing(
                    soup, current, source, config
                )

                print("[FOUND]", len(found), "candidates")

                offers.update(found)

                for link in pagination:
                    if link not in visited and link not in queue:
                        queue.append(link)

                # Détecter aussi les liens de pagination
                # présents sous forme de boutons.
                for a in soup.select("a[href]"):
                    href = normalize(urljoin(
                        current, a.get("href", "")
                    ))

                    if (
                        href
                        and allowed_domain(
                            href, config["domains"]
                        )
                        and (
                            "page=" in href
                            or "/page/" in href
                        )
                        and href not in visited
                        and href not in queue
                    ):
                        queue.append(href)

                time.sleep(DELAY)

            except PlaywrightTimeout:
                print("[TIMEOUT]", current)

            except Exception as exc:
                print("[LISTING ERROR]", current, exc)

        print(
            f"\n[DISCOVERY] {source}: "
            f"{len(offers)} offres candidates"
        )

        # Visiter les détails.
        detail_page = context.new_page()

        for index, mission in enumerate(
            list(offers.values())[:MAX_DETAILS],
            start=1
        ):

            print(
                f"[DETAIL {index}/{min(len(offers), MAX_DETAILS)}]",
                mission["url"]
            )

            mission = extract_detail(
                detail_page, mission
            )

            if mission["title"]:
                save_mission(mission)

            time.sleep(DELAY)

        detail_page.close()

    finally:
        context.close()

    print(
        f"[DONE] {source}: "
        f"{len(offers)} offres détectées"
    )

    return len(offers)


# =====================================================
# CSV EXPORT
# =====================================================

def export_csv():

    with sqlite3.connect(DB_FILE) as conn:

        rows = conn.execute("""
            SELECT
                source, title, company, location,
                description, skills, published_date,
                url, collected_at
            FROM missions
            ORDER BY collected_at DESC
        """).fetchall()

    columns = [
        "source", "title", "company", "location",
        "description", "skills", "published_date",
        "url", "collected_at"
    ]

    with open(
        CSV_FILE, "w",
        newline="", encoding="utf-8-sig"
    ) as f:

        writer = csv.writer(f)
        writer.writerow(columns)
        writer.writerows(rows)

    print("[CSV]", len(rows), "offres exportées")


# =====================================================
# GLOBAL EXECUTION
# =====================================================

def scrape_all():

    init_db()
    results = {}

    with sync_playwright() as playwright:

        browser = playwright.chromium.launch(
            headless=True
        )

        try:
            for source in SOURCES:

                try:
                    results[source] = scrape_source(
                        browser, source
                    )

                except Exception as exc:
                    print("[SOURCE ERROR]", source, exc)
                    results[source] = 0

        finally:
            browser.close()

    export_csv()

    with sqlite3.connect(DB_FILE) as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM missions"
        ).fetchone()[0]

    print("\n========== FINAL REPORT ==========")

    for source, count in results.items():
        print(source, ":", count)

    print("TOTAL SQLITE:", total)

    return results


if __name__ == "__main__":
    scrape_all()
