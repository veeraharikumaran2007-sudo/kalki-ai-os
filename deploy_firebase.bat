@echo off
title Kalki AI OS - Firebase Deployment
cd /d "%~dp0"
cls
echo ========================================================
echo        KALKI AI OS - 1-CLICK FIREBASE DEPLOYMENT
echo ========================================================
echo Target URL: https://kalki-arcues.web.app
echo Project ID: kalki-arcues
echo.
echo Currently logged in accounts:
call firebase login:list
echo.
echo --------------------------------------------------------
echo Step 1: Logging in to Google account...
echo (A browser window will open. Select your Google account and click Allow)
echo --------------------------------------------------------
call firebase login --reauth
echo.
echo Step 2: Selecting project kalki-arcues...
call firebase use kalki-arcues
echo.
echo Step 3: Deploying files from public to Firebase Hosting...
call firebase deploy --only hosting
echo.
echo ========================================================
echo Deployment complete!
echo Live Website: https://kalki-arcues.web.app
echo ========================================================
pause
