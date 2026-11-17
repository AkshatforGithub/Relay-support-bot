"""Main FastAPI application for Relay AI Support System."""

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from typing import Optional
import os

from app.api.endpoints import router
from app.core import config as settings

# Create FastAPI app
app = FastAPI(
    title="Relay AI Support System API",
    description="Backend API for the Relay AI Support System dashboard",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for dashboard
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Include API routes
app.include_router(router, prefix="/api", tags=["api"])

# Health check endpoint
@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok", "service": "relay-api"}

# Root endpoint - redirect to dashboard
@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/dashboard")

# Dashboard endpoint
@app.get("/dashboard", include_in_schema=False)
async def dashboard():
    from fastapi.responses import FileResponse
    return FileResponse("app/static/index.html")