
pip install fastapi uvicorn playwright pandas openpyxl python-dateutil

.\start_all.ps1

PS D:\ai_learning\whatsapp_scraper_1> cd backend
PS D:\ai_learning\whatsapp_scraper_1\backend> .\venv\Scripts\Activate.ps1
(venv) PS D:\ai_learning\whatsapp_scraper_1\backend> pip install -r requirements.txt
(venv) PS D:\ai_learning\whatsapp_scraper_1\backend> python main.py
or 
(venv) PS D:\ai_learning\whatsapp_scraper_1\backend> python sync_local_media.py
 


PS D:\ai_learning\whatsapp_scraper_1> cd whatsapp-zoho
PS D:\ai_learning\whatsapp_scraper_1\whatsapp-zoho> .\venv\Scripts\Activate.ps1
(venv) PS D:\ai_learning\whatsapp_scraper_1\whatsapp-zoho> uvicorn main:app --reload --port 8000


(venv) PS D:\ai_learning\whatsapp_scraper_1\backend> python server.py

PS D:\ai_learning\whatsapp_scraper_1\frontend> python -m http.server 3000
 