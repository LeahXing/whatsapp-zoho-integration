"""
API Server Module.
Exposes endpoints for the frontend interface, configures Windows Proactor loop for Playwright,
and triggers the backend main scraping pipeline asynchronously[cite: 8].
"""

import os
import sys
import asyncio
import traceback
from typing import Dict, Any, List

# FIX: Windows requires ProactorEventLoop for Playwright async subprocesses[cite: 8]
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())  # type: ignore

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config
from backend.main_1 import main as run_main_pipeline


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ScraperRequest(BaseModel):
    targetGroups: List[str]
    startDate: str
    endDate: str
    maxScrolls: int


@app.post("/api/run-scraper")
async def run_scraper_api(req: ScraperRequest) -> Dict[str, Any]:
    """
    Updates configuration from user input, executes the scraping pipeline,
    and returns file download paths[cite: 8].
    """
    try:
        config.TARGET_GROUPS = req.targetGroups
        config.START_DATE = req.startDate
        config.END_DATE = req.endDate
        config.MAX_HISTORY_SCROLLS = req.maxScrolls

        print(f"📥 Received config update: Groups={config.TARGET_GROUPS}, Scrolls={config.MAX_HISTORY_SCROLLS}")

        await run_main_pipeline()

        output_dir: str = config.MEDIA_OUTPUT_DIR
        os.makedirs(output_dir, exist_ok=True)
        
        json_url = ""
        excel_url = ""

        for file_name in os.listdir(output_dir):
            if file_name.endswith(".json") and not json_url:
                json_url = f"/downloads/{file_name}"
            elif file_name.endswith(".xlsx") and not excel_url:
                excel_url = f"/downloads/{file_name}"

        return {
            "success": True,
            "jsonUrl": json_url,
            "excelUrl": excel_url
        }

    except Exception as e:
        print("❌ Error occurred during scraping pipeline execution:")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


os.makedirs(config.MEDIA_OUTPUT_DIR, exist_ok=True)
app.mount("/downloads", StaticFiles(directory=config.MEDIA_OUTPUT_DIR), name="downloads")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8009, reload=False)