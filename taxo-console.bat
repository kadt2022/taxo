@echo off
setlocal
chcp 65001 >nul
title Taxo - console d'administration

rem ==== A adapter : depots que Taxo a le droit de lire (separes par ;) ====
set "TAXO_ALLOWED_ROOTS=D:\Taxo;D:\Taxo\taxo;D:\Taxo\demo-diff;D:\Takibu"

rem Ce fichier se place a la racine du depot Taxo (a cote de backend et frontend).
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
if not exist "%ROOT%\backend\app" (
  echo [ERREUR] Placez ce fichier a la racine du depot Taxo, a cote de backend et frontend.
  pause & exit /b 1
)
set "DATABASE_URL=sqlite:///%ROOT:\=/%/backend/taxo.db"
set "PY=%ROOT%\.venv\Scripts\python.exe"

echo === Taxo : preparation ===
where py >nul 2>nul && (set "BOOT=py -3") || (set "BOOT=python")
if not exist "%PY%" (
  echo Creation de l'environnement Python...
  %BOOT% -m venv "%ROOT%\.venv" || (echo [ERREUR] Python 3.12+ introuvable. & pause & exit /b 1)
)
"%PY%" -m pip install -q -r "%ROOT%\backend\requirements.txt" || (echo [ERREUR] Installation Python echouee. & pause & exit /b 1)

pushd "%ROOT%\backend"
"%PY%" -m alembic upgrade head || (echo [ERREUR] Migration de la base echouee. & popd & pause & exit /b 1)
popd

where npm >nul 2>nul || (echo [ERREUR] Node.js 22.12+ introuvable. & pause & exit /b 1)
if not exist "%ROOT%\frontend\node_modules" (
  echo Installation du portail...
  pushd "%ROOT%\frontend"
  call npm ci
  if errorlevel 1 (
    rem Une installation incomplete serait prise pour bonne au lancement suivant.
    rmdir /s /q node_modules 2>nul
    popd
    echo [ERREUR] Installation du portail echouee ^(npm ci^).
    pause & exit /b 1
  )
  popd
)

echo === Taxo : demarrage ===
start "Taxo API (port 8000)" /d "%ROOT%\backend" cmd /k ""%PY%" -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000"
start "Taxo portail (port 5173)" /d "%ROOT%\frontend" cmd /k "npm run dev -- --port 5173 --strictPort"

echo Attente du portail...
timeout /t 6 /nobreak >nul
start "" http://127.0.0.1:5173

echo.
echo Console d'administration : http://127.0.0.1:5173
echo API et documentation     : http://127.0.0.1:8000/docs
echo Depots autorises         : %TAXO_ALLOWED_ROOTS%
echo.
echo Pour arreter : fermez les fenetres "Taxo API" et "Taxo portail".
pause
