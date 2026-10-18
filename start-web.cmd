@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python nu este instalat sau nu este disponibil.
  pause
  exit /b 1
)
python -c "import fastapi, uvicorn, requests, tkinter, truststore" >nul 2>nul
if errorlevel 1 (
  echo Instaleaza dependentele: python -m pip install -r requirements-web.txt
  pause
  exit /b 1
)
call npm run build
if errorlevel 1 (
  echo Build nereusit. Verifica Node.js si ruleaza npm install.
  pause
  exit /b 1
)
echo.
echo Calculator: http://localhost:8000
echo Telefon: http://IP-CALCULATOR:8000 pe aceeasi retea Wi-Fi.
echo Pentru adresa IPv4 a calculatorului foloseste ipconfig.
echo Opreste serverul cu Ctrl+C.
python web_server.py --host 0.0.0.0 --port 8000
pause

