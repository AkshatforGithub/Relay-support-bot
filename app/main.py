"""Main FastAPI application for Relay AI Support System."""

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from typing import Optional
import os

from app.api.endpoints import router
from app.core.config import settings

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

# Include API routes
app.include_router(router, prefix="/api", tags=["api"])

# Health check endpoint
@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok", "service": "relay-api"}

# Root endpoint
@app.get("/", include_outline=False)
async def root():
    return {"message": "Relay AI Support System API", "docs": "/api/docs"}