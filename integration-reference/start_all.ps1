# 1. Open a new window for the Uvicorn server
Start-Process powershell -ArgumentList `
    "-NoExit", `
    "-Command", `
    "cd '.\whatsapp-zoho'; .\venv\Scripts\Activate.ps1; uvicorn main:app --reload --port 8000"

# 2. Open a second new window for the Media Sync script
Start-Process powershell -ArgumentList `
    "-NoExit", `
    "-Command", `
    "cd '.\backend'; .\venv\Scripts\Activate.ps1; python main.py"
