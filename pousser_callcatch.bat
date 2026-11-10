@echo off
set "PATH=C:\Users\levis\AppData\Local\Programs\Git\cmd;C:\Users\levis\AppData\Local\Programs\Git\mingw64\bin;%PATH%"
echo ========================================================
echo   ENVOI DE CALLCATCH AI VERS GITHUB (POUR RENDER)
echo ========================================================
echo.
git add callcatch_ai IDEES_SAAS_USA_FUTURE.txt run_callcatch.py lancer_callcatch.bat
git commit -m "feat: Add CallCatch AI (US Missed Call Text-Back SaaS)"
git push origin main
echo.
if %ERRORLEVEL% EQU 0 (
    echo ========================================================
    echo   SUCCES ! CallCatch AI est sur GitHub pret pour Render !
    echo ========================================================
) else (
    echo ========================================================
    echo   Une erreur est survenue lors de l'envoi vers GitHub.
    echo ========================================================
)
pause
