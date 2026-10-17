
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request

from app.routes.message_routes import router as message_router
from app.routes.deal_routes import router as deal_router

from app.storage.processing_state import initialize_database
from app.storage.group_conversation_state import initialize_group_conversation_tables
from app.services.note_buffer_worker import (
    start_note_buffer_worker,
    stop_note_buffer_worker,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize existing WhatsApp Notes queue tables.
    initialize_database()

    # Initialize shared group conversation and membership tables.
    initialize_group_conversation_tables()

    # Start existing background Notes worker.
    start_note_buffer_worker()

    try:
        yield
    finally:
        stop_note_buffer_worker()


app = FastAPI(
    title="WhatsApp Zoho Integration API",
    description=(
        "API for receiving WhatsApp group messages "
        "and integrating them into Zoho CRM."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    if request.method == "POST":
        print(f"\n⚡ Incoming {request.method} request to: {request.url}")

    return await call_next(request)


app.include_router(message_router)
app.include_router(deal_router)


@app.get("/")
def health_check():
    return {
        "status": "ok",
        "service": "WhatsApp Zoho Integration API",
    }
