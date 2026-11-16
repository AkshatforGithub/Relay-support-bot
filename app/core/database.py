"""Supabase database client for Relay AI Support System.

Handles Supabase client initialization and provides reusable query methods
for the Phase 1 API endpoints. Uses anon key for public endpoints and
service_role key for protected endpoints.
"""

import os
import logging
from typing import Optional
from supabase import create_client, Client

# Configure logging
logger = logging.getLogger(__name__)

# Initialize Supabase clients
# Anon key for public endpoints (anon role with RLS policies)
_supabase_anon: Optional[Client] = None
# Service role key for protected endpoints (bypasses RLS)
_supabase_service: Optional[Client] = None


def get_supabase(role: str = "anon") -> Client:
    """Get Supabase client configured for the specified role.

    Args:
        role: "anon" for public endpoints with RLS, "service_role" for protected endpoints

    Returns:
        Supabase Client instance
    """
    global _supabase_anon, _supabase_service

    if role == "anon":
        if _supabase_anon is None:
            supabase_url = os.getenv("SUPABASE_URL", "")
            supabase_anon_key = os.getenv("SUPABASE_ANON_KEY", "")

            if not supabase_url or not supabase_anon_key:
                logger.error("Supabase anon credentials not configured")

            _supabase_anon = create_client(supabase_url, supabase_anon_key)
        return _supabase_anon

    elif role == "service_role":
        if _supabase_service is None:
            supabase_url = os.getenv("SUPABASE_URL", "")
            supabase_service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

            if not supabase_url or not supabase_service_key:
                logger.error("Supabase service role credentials not configured")

            _supabase_service = create_client(supabase_url, supabase_service_key)
        return _supabase_service

    else:
        raise ValueError(f"Invalid Supabase role: {role}. Use 'anon' or 'service_role'.")


# Reusable query methods for API endpoints


def chat_id_filter(chat_id: str):
    """Create a chat_id filter for Supabase queries.

    This is a placeholder for the RLS chat_id-scope policy evaluation.
    In production, the Supabase client would apply the chat_id filter
    based on the authenticated user's session context.
    """
    return {"chat_id": chat_id}  # Simplified for documentation


def count_only(query_result) -> int:
    """Extract count from Supabase query result.

    Handles both count='exact' and standard count responses.
    """
    if hasattr(query_result, 'count'):
        return query_result.count
    elif hasattr(query_result, 'data'):
        return len(query_result.data) if query_result.data else 0
    return 0