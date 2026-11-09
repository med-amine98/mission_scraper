import re
import io
import zipfile
import zlib
import xml.etree.ElementTree as ET
from typing import Dict, List, Any

# ============================================================
# IT SKILLS & KEYWORDS DICTIONARY
# ============================================================
TECH_SKILLS = [
    # Languages
    "python", "java", "javascript", "typescript", "c++", "c#", ".net", "php", "golang", "go",
    "rust", "ruby", "scala", "kotlin", "swift", "sql", "bash", "shell", "powershell", "html", "css",
    # Frontend
    "react", "react.js", "react native", "angular", "angularjs", "vue", "vue.js", "next.js", "nuxt", "svelte",
    "tailwind", "bootstrap", "sass", "redux", "graphql",
    # Backend & Frameworks
    "fastapi", "flask", "django", "spring", "spring boot", "node.js", "nodejs", "node", "express", "express.js",
    "nest.js", "nestjs", "symfony", "laravel", "asp.net", "hibernate", "sqlalchemy", "rest api", "api rest",
    # Cloud & DevOps
    "docker", "kubernetes", "k8s", "aws", "azure", "gcp", "google cloud", "terraform", "ansible",
    "jenkins", "gitlab ci", "github actions", "ci/cd", "helm", "prometheus", "grafana", "linux", "unix",
    # Data & AI
    "data engineer", "data analyst", "data science", "data scientist", "machine learning",
    "deep learning", "ia", "intelligence artificielle", "nlp", "llm", "generative ai", "ia générative",
    "pandas", "numpy", "matplotlib", "scikit-learn", "tensorflow", "pytorch", "spark", "pyspark", "kafka",
    "hadoop", "databricks", "snowflake", "power bi", "tableau", "dbt", "airflow", "elastic", "elasticsearch",
    "computer vision", "opencv", "yolo", "reinforcement learning", "gnn",
    # Databases
    "postgresql", "postgres", "mysql", "mariadb", "oracle", "sql server", "mongodb",
    "redis", "cassandra", "dynamodb", "neo4j", "sqlite", "qdrant",
    # Architecture & Tools
    "microservices", "api rest", "soap", "architecture", "agile", "scrum", "kanban",
    "jira", "git", "devsecops", "cybersecurité", "cybersecurity", "iso 27001", "rgpd",
    "sap", "salesforce", "servicenow", "cobol", "cics", "mainframe", "openstack", "vmware",
    "chef de projet", "product owner", "scrum master", "business analyst", "qa", "selenium",
    "cypress", "testeur", "istqb", "commvault", "bi"
]

COMMON_TITLES = [
    "développeur full stack", "developpeur fullstack", "développeur backend", "développeur frontend",
    "développeur python", "développeur java", "développeur react", "développeur .net",
    "ingénieur en informatique", "ingenieur informatique", "ingénieur logiciel",
    "data engineer", "data analyst", "data scientist", "ingénieur ia", "architecte ia",
    "architecte cloud", "ingénieur devops", "ingénieur cloud", "chef de projet it",
    "chef de projet digital", "product owner", "scrum master", "business analyst",
    "consultant sap", "consultant cybersecurité", "administrateur système",
    "administrateur réseau", "tech lead", "lead dev", "qa engineer", "consultant data"
]

def extract_pdf_text_robust(content: bytes) -> str:
    """
    Decodes modern PDF files (including Microsoft Print To PDF, Adobe, Word)
    by parsing embedded ToUnicode CMaps and content stream text operators.
    """
    merged_cmap = {}
    stream_regex = re.compile(rb'stream[\r\n]+(.*?)[\r\n]+endstream', re.DOTALL)
    
    # 1. Parse all ToUnicode CMaps
    for m in re.finditer(rb'begincmap(.*?)endcmap', content, re.DOTALL):
        cmap_body = m.group(1)
        for bfchar_block in re.findall(rb'beginbfchar(.*?)endbfchar', cmap_body, re.DOTALL):
            hex_tokens = re.findall(rb'<([0-9a-fA-F]+)>', bfchar_block)
            for i in range(0, len(hex_tokens) - 1, 2):
                try:
                    src = int(hex_tokens[i], 16)
                    dst_bytes = bytes.fromhex(hex_tokens[i+1].decode('ascii'))
                    char = dst_bytes.decode('utf-16-be', errors='ignore')
                    merged_cmap[src] = char
                except Exception:
                    pass

        for bfrange_block in re.findall(rb'beginbfrange(.*?)endbfrange', cmap_body, re.DOTALL):
            tokens = re.findall(rb'<([0-9a-fA-F]+)>', bfrange_block)
            for i in range(0, len(tokens) - 2, 3):
                try:
                    start = int(tokens[i], 16)
                    end = int(tokens[i+1], 16)
                    dst_start = int(tokens[i+2], 16)
                    for code in range(start, end + 1):
                        merged_cmap[code] = chr(dst_start + (code - start))
                except Exception:
                    pass

    # 2. Extract content text streams
    text_blocks = []
    for s in stream_regex.findall(content):
        try:
            dec = zlib.decompress(s)
        except Exception:
            continue
        if b'BT' not in dec:
            continue

        lines = dec.split(b'\n')
        for line in lines:
            line_str = line.decode('latin-1', errors='ignore')
            if 'TJ' in line_str or 'Tj' in line_str:
                tokens = re.findall(r'<([0-9a-fA-F]+)>|\((.*?)\)', line_str)
                decoded_line = []
                for hex_part, str_part in tokens:
                    if hex_part:
                        if len(hex_part) % 4 == 0:
                            for i in range(0, len(hex_part), 4):
                                g = int(hex_part[i:i+4], 16)
                                decoded_line.append(merged_cmap.get(g, ''))
                        elif len(hex_part) % 2 == 0:
                            for i in range(0, len(hex_part), 2):
                                g = int(hex_part[i:i+2], 16)
                                decoded_line.append(merged_cmap.get(g, chr(g)))
                    elif str_part:
                        decoded_line.append(str_part)
                txt = ''.join(decoded_line).strip()
                # Exclude unprintable font headers
                if txt and not any(ord(c) < 32 and c not in '\r\n\t' for c in txt):
                    text_blocks.append(txt)

    raw_joined = '\n'.join(text_blocks)
    
    # Filter out binary or unprintable lines
    clean_lines = []
    for line in raw_joined.split('\n'):
        line_s = line.strip()
        if not line_s:
            continue
        alphanumeric_count = sum(1 for c in line_s if c.isalnum() or c.isspace() or c in ",.-()/'\"@:;!?_")
        if alphanumeric_count >= len(line_s) * 0.75:
            clean_lines.append(line_s)

    result = '\n'.join(clean_lines).strip()
    return result[:40000]


def extract_text_from_bytes(content: bytes, filename: str = "") -> str:
    """Extract plain text from file bytes (PDF, DOCX, TXT)."""
    filename_lower = filename.lower()
    
    # 1. PDF extraction
    if filename_lower.endswith(".pdf") or content.startswith(b"%PDF"):
        pdf_text = extract_pdf_text_robust(content)
        if len(pdf_text) > 30:
            return pdf_text
        # Fallback to plain text strings if uncompressed PDF
        ascii_matches = re.findall(rb"\((.*?)\)\s*Tj", content)
        if ascii_matches:
            simple_text = " ".join([m.decode("latin-1", errors="ignore") for m in ascii_matches if len(m) > 1])
            if len(simple_text) > 50:
                return simple_text[:40000]
        return ""

    # 2. DOCX via built-in zipfile
    if filename_lower.endswith(".docx") or content.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as z:
                if "word/document.xml" in z.namelist():
                    xml_content = z.read("word/document.xml")
                    tree = ET.fromstring(xml_content)
                    paragraphs = []
                    for p in tree.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"):
                        texts = [t.text for t in p.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t") if t.text]
                        if texts:
                            paragraphs.append("".join(texts))
                    extracted = "\n".join(paragraphs).strip()
                    if extracted:
                        return extracted[:40000]
        except Exception:
            pass

    # 3. Direct UTF-8 / Latin-1 decode for TXT / Markdown
    try:
        return content.decode("utf-8")[:40000]
    except UnicodeDecodeError:
        try:
            return content.decode("latin-1")[:40000]
        except Exception:
            return content.decode("utf-8", errors="ignore")[:40000]


def parse_cv_profile(raw_text: str, filename: str = "") -> Dict[str, Any]:
    """Parse candidate text to extract name, contact info, skills, and experience."""
    text_clean = raw_text.replace("\r", "\n")
    lines = [line.strip() for line in text_clean.split("\n") if line.strip()]
    
    # Filter out boilerplate / copyright lines from start
    meaningful_lines = []
    for line in lines:
        l_lower = line.lower()
        if any(bp in l_lower for bp in [
            "copyright", "reproduction et diffusion", "droits réservés", "all rights reserved",
            "page 1", "page 2", "curriculum vitae", "consulting 2017", "consulting 20"
        ]):
            continue
        meaningful_lines.append(line)

    # 1. Email extraction (strict ASCII email regex)
    email_match = re.search(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", raw_text)
    email = email_match.group(0) if email_match else ""

    # 2. Phone extraction (French / International numbers)
    phone = ""
    phone_matches = re.findall(r"(?:(?:\+|00)\s*(?:33|216|32|41)|0)\s*[1-9](?:[\s.-]*\d{2}){4}", raw_text)
    if phone_matches:
        phone = re.sub(r"\s+", " ", phone_matches[0]).strip()

    # 3. Name heuristic (inspect top meaningful lines)
    name = ""
    for line in meaningful_lines[:6]:
        line_clean = re.sub(r"[^\w\s-]", "", line).strip()
        words = line_clean.split()
        if (
            2 <= len(words) <= 4
            and not words[0].isdigit()
            and not any(char.isdigit() for char in line_clean)
            and not any(k in line.lower() for k in [
                "ingénieur", "développeur", "developer", "senior", "junior", "docteur", "profil",
                "consultant", "stage", "expérience", "titulaire", "compétences", "technologies"
            ])
        ):
            name = line.strip()
            break

    if not name:
        base_name = re.sub(r"\.[^.]+$", "", filename or "Candidat")
        name = base_name.replace("_", " ").replace("-", " ").title()

    # 4. Target title extraction
    title = ""
    for line in meaningful_lines[:8]:
        line_lower = line.lower()
        # Exclude name line
        if line.strip() == name:
            continue
        for t in COMMON_TITLES:
            if t in line_lower:
                title = line.strip()
                break
        if title:
            break

    if not title:
        for line in meaningful_lines[:6]:
            if line.strip() == name:
                continue
            if any(k in line.lower() for k in ["ingénieur", "développeur", "architecte", "consultant", "lead", "data"]):
                title = line.strip()
                break

    if not title:
        title = "Ingénieur en informatique / Consultant IT"

    # Clean title from weird prefix/suffixes
    title = re.sub(r"^[^a-zA-ZÀ-ÿ]+", "", title).strip()

    # 5. Experience years
    exp_years = 0
    exp_matches = re.findall(r"(\d+)\s*(?:\+)?\s*(?:ans?|années?|years?)\s*(?:d['’]expérience)?", raw_text, re.IGNORECASE)
    if exp_matches:
        try:
            years = [int(y) for y in exp_matches if 0 < int(y) <= 40]
            if years:
                exp_years = max(years)
        except Exception:
            pass

    # 6. Technical skills detection
    raw_lower = raw_text.lower()
    detected_skills = []
    for skill in TECH_SKILLS:
        pattern = r"(?<![a-zA-Z0-9])" + re.escape(skill) + r"(?![a-zA-Z0-9])"
        if re.search(pattern, raw_lower):
            detected_skills.append(skill.capitalize() if len(skill) > 3 else skill.upper())

    unique_skills = []
    for s in detected_skills:
        if s not in unique_skills:
            unique_skills.append(s)

    # 7. Summary
    summary = ""
    for line in meaningful_lines:
        line_s = line.strip()
        if len(line_s) > 60 and not line_s.startswith("http") and "@" not in line_s and line_s != name:
            summary = line_s
            break
    if not summary and meaningful_lines:
        for l in meaningful_lines:
            if l != name and len(l) > 20:
                summary = l[:250]
                break

    return {
        "name": name,
        "title": title,
        "email": email,
        "phone": phone,
        "experience_years": exp_years,
        "skills": ", ".join(unique_skills),
        "skills_list": unique_skills,
        "summary": summary,
        "raw_text": raw_text[:30000],
        "filename": filename
    }


def extract_mission_skills(mission: Dict[str, Any]) -> List[str]:
    """Extract standard IT skills required by a mission."""
    existing_skills = mission.get("skills") or ""
    title = mission.get("title") or ""
    desc = mission.get("description") or ""

    primary_text = f"{existing_skills} {title}".lower()
    primary_found = []
    for skill in TECH_SKILLS:
        pattern = r"(?<![a-zA-Z0-9])" + re.escape(skill) + r"(?![a-zA-Z0-9])"
        if re.search(pattern, primary_text):
            primary_found.append(skill.capitalize() if len(skill) > 3 else skill.upper())

    desc_found = []
    desc_lower = desc.lower()[:5000]  # Limit to first 5000 chars of description
    for skill in TECH_SKILLS:
        pattern = r"(?<![a-zA-Z0-9])" + re.escape(skill) + r"(?![a-zA-Z0-9])"
        if re.search(pattern, desc_lower):
            desc_found.append(skill.capitalize() if len(skill) > 3 else skill.upper())

    combined = []
    for s in primary_found + desc_found:
        if s not in combined:
            combined.append(s)
            if len(combined) >= 12:
                break

    return combined


def compute_match_score(cv: Dict[str, Any], mission: Dict[str, Any]) -> Dict[str, Any]:
    """
    Computes matching score between a candidate CV and a mission offer.
    Fast and robust evaluation (sub-millisecond).
    """
    mission_skills = extract_mission_skills(mission)
    
    cv_skills_raw = cv.get("skills") or ""
    cv_text = ((cv.get("raw_text") or "")[:10000] + " " + cv_skills_raw + " " + (cv.get("title") or "")).lower()
    
    cv_skills = []
    for skill in TECH_SKILLS:
        pattern = r"(?<![a-zA-Z0-9])" + re.escape(skill) + r"(?![a-zA-Z0-9])"
        if re.search(pattern, cv_text):
            cv_skills.append(skill.capitalize() if len(skill) > 3 else skill.upper())

    # 1. Skills overlap (50 points)
    matched_skills = []
    missing_skills = []
    
    if mission_skills:
        for ms in mission_skills:
            if any(ms.lower() == cs.lower() for cs in cv_skills):
                matched_skills.append(ms)
            else:
                missing_skills.append(ms)

        coverage = len(matched_skills) / len(mission_skills)
        skill_score = coverage * 50
    else:
        matched_skills = cv_skills[:4]
        skill_score = 30

    # 2. Title & Role relevance (25 points)
    mission_title = (mission.get("title") or "").lower()
    cv_title = (cv.get("title") or "").lower()
    title_score = 10
    
    title_tokens_mission = [w for w in re.findall(r"\w+", mission_title) if len(w) > 3]
    title_tokens_cv = [w for w in re.findall(r"\w+", cv_title) if len(w) > 3]
    
    if title_tokens_mission and title_tokens_cv:
        common_words = set(title_tokens_mission).intersection(set(title_tokens_cv))
        meaningful_common = [w for w in common_words if w not in ["pour", "avec", "dans", "chez", "plus", "missions", "mission"]]
        if meaningful_common:
            title_score = min(25, 14 + len(meaningful_common) * 6)
    
    # 3. Experience alignment (15 points)
    exp_years = cv.get("experience_years") or 0
    mission_text = (mission.get("description") or "")[:4000].lower() + " " + mission_title
    
    req_senior = any(k in mission_text for k in ["senior", "lead", "expert", "10 ans", "7 ans", "8 ans", "architecte"])
    req_junior = any(k in mission_text for k in ["junior", "débutant", "1 an", "2 ans", "alternance", "stage"])
    
    exp_score = 10
    exp_fit = "Expérience adaptée"
    if req_senior:
        if exp_years >= 5:
            exp_score = 15
            exp_fit = f"Parfaitement adapté ({exp_years} ans d'expérience - Profil Senior)"
        elif exp_years >= 3:
            exp_score = 10
            exp_fit = f"Expérience intermédiaire ({exp_years} ans pour un besoin Senior)"
        else:
            exp_score = 5
            exp_fit = f"Profil un peu junior ({exp_years} ans) pour une mission Senior"
    elif req_junior:
        if 0 <= exp_years <= 3:
            exp_score = 15
            exp_fit = f"Niveau d'expérience idéal ({exp_years} ans)"
        else:
            exp_score = 12
            exp_fit = f"Profil expérimenté ({exp_years} ans)"
    else:
        if exp_years >= 3:
            exp_score = 14
            exp_fit = f"{exp_years} ans d'expérience"
        else:
            exp_score = 10
            exp_fit = f"{exp_years} ans d'expérience"

    # 4. Text / Domain context overlap (10 points)
    mission_desc_words = set([w for w in re.findall(r"\w{4,}", mission_text) if len(w) > 3])
    cv_desc_words = set([w for w in re.findall(r"\w{4,}", cv_text[:8000]) if len(w) > 3])
    context_overlap = len(mission_desc_words.intersection(cv_desc_words))
    context_score = min(10, max(2, context_overlap // 3))

    # Total score
    total_score = int(round(skill_score + title_score + exp_score + context_score))
    total_score = max(5, min(99, total_score))
    
    # Verdict
    if total_score >= 80:
        verdict = "Candidat Idéal"
        badge_class = "score-excellent"
        recommendation = "Recommandation forte : adéquation technique et rôle optimale pour cette mission."
    elif total_score >= 65:
        verdict = "Très Bon Match"
        badge_class = "score-good"
        recommendation = "Profil solide avec les compétences clés recherchées. Entretien recommandé."
    elif total_score >= 45:
        verdict = "Match Partiel"
        badge_class = "score-medium"
        recommendation = "Plusieurs compétences clés en commun, vérifier les prérequis complémentaires."
    else:
        verdict = "Adéquation Faible"
        badge_class = "score-low"
        recommendation = "Profil éloigné des exigences techniques ou métier de l'offre."

    return {
        "score": total_score,
        "verdict": verdict,
        "badge_class": badge_class,
        "matched_skills": matched_skills,
        "missing_skills": missing_skills,
        "experience_fit": exp_fit,
        "recommendation": recommendation,
        "details": {
            "skill_score": round(skill_score, 1),
            "title_score": title_score,
            "exp_score": exp_score,
            "context_score": context_score
        }
    }
