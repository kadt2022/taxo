@echo off
rem ============================================================
rem  Taxo + Minia avec la lecture du code d'un symbole (get_source)
rem
rem  Pour les essais uniquement. Le code n'est lu que si les DEUX
rem  consentements sont donnes (ARCHITECTURE, 12.6) :
rem    1. ce reglage serveur, TAXO_SOURCE_READING=symbol (defaut : off) ;
rem    2. l'accord de chaque question ("source": true, ou la case du portail).
rem  Les secrets et les identites sont masques avant l'envoi a un modele.
rem
rem  Place ce fichier a la racine du depot Taxo. Il lance la console
rem  habituelle : taxo-console-corrige.bat si elle existe, sinon
rem  taxo-console.bat, avec le reglage ci-dessous en plus.
rem ============================================================
set "TAXO_SOURCE_READING=symbol"

if exist "%~dp0taxo-console-corrige.bat" (
  call "%~dp0taxo-console-corrige.bat"
) else if exist "%~dp0taxo-console.bat" (
  call "%~dp0taxo-console.bat"
) else (
  echo [ERREUR] Aucune console Taxo trouvee a cote de ce fichier.
  pause
  exit /b 1
)
