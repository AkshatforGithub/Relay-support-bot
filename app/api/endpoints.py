"""Phase 1 API Endpoints for Relay AI Support System.

Implements all required endpoints as per the technical review plan.
Authentication: X-API-Key header checked against ADMIN_API_KEY in .env.
Supabase service_role key used server-side for all DB operations.
No anon key or RLS logic.
"""

from fastapi import Header, APIRouter, Depends, HTTPException, status, Query
from typing import Optional, List
from pydantic import BaseModel, Field
import logging
import os
import re

from app.core.config import POLLING_INTERVALS
from app.core.database import get_supabase

logger = logging.getLogger(__name__)

router = APIRouter(tags=["api"])

# --- API Key Authentication ---

ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")


async def get_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    """Validate X-API-Key header against ADMIN_API_KEY in .env.

    All routes require this header for authorization.
    """
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header",
        )
    if not ADMIN_API_KEY or x_api_key != ADMIN_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid X-API-Key",
        )
    return x_api_key


# --- Response Models ---


class ErrorResponse(BaseModel):
    """Standard error response model."""
    success: bool = False
    error: str = Field(..., description="Error message")
    data: Optional[object] = None


class SuccessResponse(BaseModel):
    """Standard success response model."""
    success: bool = True
    data: object
    error: Optional[str] = None


# --- API Contract Models ---


class ConversationHistory(BaseModel):
    """Response model for conversation history endpoint."""
    chatId: str
    query: str
    username: Optional[str] = None
    correlationId: Optional[str] = None
    chatHistory: List[dict]
    lastAssistantAnswer: Optional[str] = None
    assistantCategory: Optional[str] = None
    needsEscalation: bool = False
    escalationAlreadyOpen: bool = False
    usedOrderId: Optional[str] = None
    usedEmail: Optional[str] = None
    status: str  # one of: approved, escalation_already_open, out_of_scope, error


class TicketItem(BaseModel):
    """Response model for ticket item."""
    id: int
    parent_chat_id: str
    summary: str
    category: Optional[str] = None
    status: str  # pending, in_progress, resolved
    created_at: str
    resolved_at: Optional[str] = None
    resolved_by: Optional[str] = None


class TicketsResponse(BaseModel):
    """Response model for tickets list endpoint."""
    tickets: List[TicketItem]
    total: int
    page: int
    perPage: int


class SystemStatsResponse(BaseModel):
    """Response model for system stats endpoint."""
    # Live computed values from Supabase
    total_tickets: int
    pending_tickets: int
    resolved_tickets: int
    escalation_rate: int
    active_conversations_30d: int

    # Test-bench metrics from case-study.md (hardcoded benchmark values)
    test_bench: dict = Field(
        ..., description="Test-bench metrics from case-study.md labeled as test-results"
    )


class ResolveTicketRequest(BaseModel):
    """Request model for resolve-ticket endpoint."""
    ticketId: int = Field(..., description="ID of ticket to resolve")
    resolvedBy: str = Field(..., description="User or system resolving the ticket")


# --- API Endpoints ---


@router.get(
    "/conversations/{chatId}",
    response_model=ConversationHistory,
    tags=["conversations"],
)
async def get_conversation(
    chatId: str,
    x_api_key: str = Depends(get_api_key),
    supabase=Depends(get_supabase),
):
    """Get conversation history and status for a chat.

    Re-derives Brain/Critic status from persistable fields only.
    Uses chat_id-scope data access via Supabase service_role key.
    """
    try:
        # Query chat_memory for last 10 messages ordered by created_at DESC
        memory_response = supabase.table("chat_memory")\
            .select("*")\
            .chat_id_chat_id_chat(chatId)\
            .order("created_at", desc=True)\
            .limit(10)\
            .execute()

        chat_history = memory_response.data or []

        # Re-derive usedOrderId from query text pattern ORD-?\d+
        # Re-derive usedEmail from query text pattern \w+@\w+\.\w+
        # These would typically come from the original user query
        # For now, re-derive from the most recent user message
        usedOrderId: Optional[str] = None
        usedEmail: Optional[str] = None

        if chat_history:
            latest_messages = [m for m in chat_history if m.get("role") == "user"]
            if latest_messages:
                latest_user_msg = latest_messages[0].get("content", "")
                # Pattern: ORD-?\d+
                order_match = re.search(r'ORD-?\\d+', latest_user_msg)
                if order_match:
                    usedOrderId = order_match.group(0)
                # Pattern: \w+@\w+\.\w+
                email_match = re.search(r'\w+@\w+\.\w+', latest_user_msg)
                if email_match:
                    usedEmail = email_match.group(0)

        # Check escalation already open via follow_up_tickets
        ticket_response = supabase.table("follow_up_tickets")\
            .select("status, resolved_at, resolved_by")\
            .parent_chat_id_parent_chat_id(chatId)\
            .order("created_at", desc=True)\
            .limit(1)\
            .execute()

        escalationAlreadyOpen = len(ticket_response.data) > 0 and \
            ticket_response.data[0].get("status") == "pending"

        # Determine status based on data
        status_val = "approved"
        if escalationAlreadyOpen:
            status_val = "escalation_already_open"

        # Build response per revised Brain/Critic contract
        conversation = ConversationHistory(
            chatId=chatId,
            query="",  # Would come from context
            username=None,
            correlationId=None,
            chatHistory=chat_history,
            lastAssistantAnswer=None,  # Would derive from chat_memory
            assistantCategory=None,  # Would derive
            needsEscalation=False,  # Would compute
            escalationAlreadyOpen=escalationAlreadyOpen,
            usedOrderId=usedOrderId,
            usedEmail=usedEmail,
            status=status_val,
        )

        return conversation

    except Exception as e:
        logger.error(f"Error fetching conversation {chatId}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch conversation data",
        )


@router.get(
    "/tickets",
    response_model=TicketsResponse,
    tags=["tickets"],
)
async def get_tickets(
    status: Optional[str] = Query(None, description="Filter by ticket status"),
    category: Optional[str] = Query(None, description="Filter by ticket category"),
    parent_chat_id: Optional[str] = Query(None, description="Filter by parent chat ID"),
    page: int = Query(1, ge=1, description="Page number"),
    perPage: int = Query(20, ge=1, le=100, description="Items per page"),
    x_api_key: str = Depends(get_api_key),
    supabase=Depends(get_supabase),
):
    """Get list of follow-up tickets with optional filters.

    Supports filtering by status, category, and parent_chat_id.
    Pagination via page and perPage query parameters.
    """
    try:
        # Build query
        query = supabase.table("follow_up_tickets").select("*", count="exact")

        # Apply filters
        if parent_chat_id:
            query = query.eq("parent_chat_id", parent_chat_id)
        if status:
            query = query.eq("status", status)
        if category:
            query = query.eq("category", category)

        # Order by created_at DESC
        query = query.order("created_at", desc=True)

        # Apply pagination
        start = (page - 1) * perPage
        query = query.range(start, start + perPage - 1)

        response = query.execute()

        tickets = [
            TicketItem(
                id=ticket["id"],
                parent_chat_id=ticket["parent_chat_id"],
                summary=ticket["summary"],
                category=ticket.get("category"),
                status=ticket.get("status"),
                created_at=ticket.get("created_at"),
                resolved_at=ticket.get("resolved_at"),
                resolved_by=ticket.get("resolved_by"),
            )
            for ticket in response.data or []
        ]

        return TicketsResponse(
            tickets=tickets,
            total=response.count or 0,
            page=page,
            perPage=perPage,
        )

    except Exception as e:
        logger.error(f"Error fetching tickets: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch ticket data",
        )


@router.get(
    "/system-stats",
    response_model=SystemStatsResponse,
    tags=["system"],
)
def get_system_stats(
    x_api_key: str = Depends(get_api_key),
    supabase=Depends(get_supabase),
):
    """Get system operational metrics.

    Computes ticket counts, escalation rate, and active conversations
    from the database tables. Returns test-bench metrics from case-study.md
    in a separate "benchmark" object labeled as test-results.
    """
    try:
        # Compute ticket counts from follow_up_tickets table
        tickets_query = supabase.table("follow_up_tickets").select("status", count="exact")
        tickets_result = tickets_query.execute()
        total_tickets = tickets_result.count or 0

        # Compute resolved tickets count
        resolved_query = supabase.table("follow_up_tickets")\
            .select("status", count="exact")\
            .eq("status", "resolved")\
            .execute()
        resolved_tickets = resolved_query.count or 0

        # Compute pending tickets (not resolved)
        pending_tickets = total_tickets - resolved_tickets

        # Compute escalation rate: 100 * total_tickets / distinct chat_ids in chat_memory
        # 0 when there are no chats
        from datetime import datetime, timedelta
        thirty_days_ago = (datetime.utcnow() - timedelta(days=30)).isoformat()

        # Select only chat_id column and paginate with range() to avoid 1000-row truncation
        distinct_chat_ids = set()
        # Use a large range to ensure we get all chat_ids (default limit is 1000)
        for i in range(0, 100000, 1000):
            end = min(i + 1000, 100001)
            query = supabase.table("chat_memory")\
                .select("chat_id")\
                .range(i, end - 1)\
                .gt("created_at", thirty_days_ago)\
                .execute()
            for msg in (query.data or []):
                cid = msg.get("chat_id")
                if cid:
                    distinct_chat_ids.add(cid)
            # Stop as soon as a page returns fewer than 1000 rows
            if len(query.data or []) < 1000:
                break
        distinct_count = len(distinct_chat_ids)

        if total_tickets > 0 and distinct_count > 0:
            escalation_rate = round(100 * total_tickets / distinct_count, 1)
        else:
            escalation_rate = 0

        # Compute active conversations (distinct chat_ids with messages in last 30 days)
        active_conversations_30d = distinct_count

        # Test-bench metrics from case-study.md
        # These are simulated benchmark values, not computed from tables
        test_bench = {
            "dupesSuppressed": 100,       # test-bench: 100% duplicate suppression
            "rateLimitFalsePositives": 0, # test-bench: 0% false positives
            "silentFailures": 0,          # architectural guarantee: 0% silent failures
            "medianResponseTime": 4.8,    # test-bench: 4.8s median
            "p95ResponseTime": 11.2,      # test-bench: 11.2s P95
            "criticFirstPassApproval": 83,# test-bench: 83% critic approval
            "autoResolutionRate": 61,     # test-bench: 61% auto-resolution
            "escalationRate": 17,         # test-bench: 17% escalation rate
        }

        # Build the response
        stats = SystemStatsResponse(
            total_tickets=total_tickets,
            pending_tickets=pending_tickets,
            resolved_tickets=resolved_tickets,
            escalation_rate=escalation_rate,
            active_conversations_30d=active_conversations_30d,
            test_bench=test_bench,
        )

        return stats

    except Exception as e:
        logger.error(f"Error fetching system stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch system statistics",
        )


@router.post(
    "/resolve-ticket",
    response_model=SuccessResponse,
    tags=["resolve-ticket"],
)
async def resolve_ticket(
    request: ResolveTicketRequest,
    x_api_key: str = Depends(get_api_key),
    supabase=Depends(get_supabase),
):
    """Resolve a follow-up ticket.

    Requires X-API-Key auth (service_role used server-side for Supabase).
    Updates ticket status to 'resolved' in Supabase with resolved_at and resolved_by.
    Posts a message to SLACK_WEBHOOK_URL if set. No responseUrl parameter.
    """
    try:
        ticket_id = request.ticketId
        resolved_by = request.resolvedBy

        # Validate ticket exists
        ticket_response = supabase.table("follow_up_tickets")\
            .select("*")\
            .eq("id", ticket_id)\
            .execute()

        if not ticket_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Ticket {ticket_id} not found",
            )

        # Update ticket status to resolved with resolved_at and resolved_by
        update_response = supabase.table("follow_up_tickets")\
            .update({
                "status": "resolved",
                "resolved_at": __import__("datetime").datetime.utcnow().isoformat(),
                "resolved_by": resolved_by,
            })\
            .eq("id", ticket_id)\
            .execute()

        # Invoke Slack webhook for notification if webhook URL is set
        # No responseUrl parameter - just post ticket resolution info
        webhook_url = os.getenv("SLACK_WEBHOOK_URL", "")
        if webhook_url:
            import httpx
            webhook_payload = {
                "ticketId": ticket_id,
                "resolvedBy": resolved_by,
                "status": "resolved",
                "timestamp": update_response.data[0].get("resolved_at"),
            }
            try:
                async with httpx.AsyncClient() as client:
                    await client.post(webhook_url, json=webhook_payload, timeout=10)
            except Exception as webhook_error:
                logger.warning(f"Slack webhook failed: {webhook_error}")
                # Don't fail the ticket resolution if webhook fails

        return SuccessResponse(
            success=True,
            data={"ticketId": ticket_id, "status": "resolved"},
            error=None,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resolving ticket {ticket_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to resolve ticket",
        )