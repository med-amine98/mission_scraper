@echo off
echo ========================================================
echo   Lancement de I-Lead Mission Scraper ^& Matching CV
echo ========================================================
echo.

start "I-Lead Backend (FastAPI)" cmd /k ".\venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000"
timeout /t 3 /nobreak >nul

start "I-Lead Frontend (React/Vite)" cmd /k "cd frontend\frontend && npm run dev"

echo Backend lance sur http://127.0.0.1:8000
echo Frontend lance sur http://localhost:5173
echo.
pause
