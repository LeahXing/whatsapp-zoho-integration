# ============================================================
# WhatsApp → Zoho CRM Integration API
# ============================================================

from fastapi import FastAPI, Request
from app.routes.message_routes import router as message_router


# ============================================================
# FastAPI Application Initialization
# ============================================================

app = FastAPI(
    title="WhatsApp Zoho Integration API",
    description=(
        "API for receiving WhatsApp group messages "
        "and integrating them into Zoho CRM."
    ),
    version="1.0.0"
)


# ============================================================
# Middleware for Request Printing & Debugging
# ============================================================

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """
    Middleware to log incoming requests directly to the terminal console.
    """
    if request.method == "POST":
        print(f"\n⚡ Incoming {request.method} request to: {request.url}")
    
    response = await call_next(request)
    return response


# ============================================================
# Register API Routes
# ============================================================

# Included without an extra prefix to prevent route duplication:
# Resolves to: http://127.0.0.1:8000/api/v1/messages/
app.include_router(message_router)


# ============================================================
# Health Check Endpoint
# ============================================================

@app.get("/")
def health_check():
    return {
        "status": "ok",
        "service": "WhatsApp Zoho Integration API"
    }