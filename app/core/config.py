"""Configuration settings for Relay AI Support System."""

import os
from pathlib import Path

# Base directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Supabase configuration
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

# Authentication
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "").split(",") if os.getenv("ALLOWED_ORIGINS") else []

# Server configuration
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
DEBUG = os.getenv("DEBUG", "False").lower() == "true"

# API settings
API_V1_STR = "/api/v1"
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3

# Polling intervals (seconds)
POLLING_INTERVALS = {
    "system_stats": 300,      # 5 minutes
    "ticket_list": 60,        # 1 minute
    "conversation_status": 30, # 30 seconds
    "brain_status": 60,       # 1 minute
}

# Error messages
ERROR_MESSAGES = {
    "invalid_chat_id": "Invalid chat ID format",
    "access_denied": "Access denied - insufficient permissions",
    "resource_not_found": "Resource not found",
    "supabase_unavailable": "Supabase service unavailable",
}