import pandas as pd

from fastapi import FastAPI, UploadFile, File, HTTPException

from database import (
    init_db,
    get_missions,
    save_mission
)

from scraper import scrape_source
from analyzer import analyze_all

app = FastAPI(
    title="I-Lead Mission Scraper",
    version="1.0"
)


@app.on_event("startup")
def startup():
    init_db()


@app.get("/")
def home():
    return {
        "project": "I-Lead Mission Scraper",
        "status": "running"
    }


@app.get("/missions")
def missions():
    return get_missions()


@app.post("/scrape/{source}")
def scrape(source: str):
    try:
        count = scrape_source(source)
        return {
            "source": source,
            "offers_processed": count
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


@app.post("/analyze")
def analyze():
    analyze_all()
    return {"message": "Analysis completed"}


@app.post("/import/csv")
async def import_csv(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=400,
            detail="Veuillez envoyer un fichier CSV"
        )

    try:
        df = pd.read_csv(file.file)
        df = df.fillna("")

        required = ["title", "description", "url"]

        if not all(col in df.columns for col in required):
            raise HTTPException(
                status_code=400,
                detail=f"Colonnes obligatoires : {required}"
            )

        count = 0

        for _, row in df.iterrows():
            save_mission({
                "source": row.get("source", "CSV"),
                "title": row.get("title", ""),
                "description": row.get("description", ""),
                "location": row.get("location", ""),
                "skills": row.get("skills", ""),
                "rate": row.get("rate", ""),
                "published_date": row.get(
                    "published_date", ""
                ),
                "url": row.get("url", "")
            })
            count += 1

        return {
            "message": "Import terminé",
            "rows_processed": count
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )