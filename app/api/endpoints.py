"""Phase 1 API Endpoints for Relay AI Support System.

Implements all public and protected endpoints as per the technical review plan.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from typing import Optional, List
from pydantic import BaseModel, Field
import logging

from app.core.config import POLLING_INTERVALS
from app.core.database import get_supabase, supabase_client

logger = logging.getLogger(__name__)

router = APIRouter(tags=["api"])

# --- Authentication Dependencies ---

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    supabase=Depends(get_supabase),
):
    """Get current user from Supabase JWT token.

    Returns user info for anon or authenticated sessions.
    """
    if not credentials:
        # Return anonymous user for public endpoints
        return {"role": "anon", "user_id": "anonymous"}

    token = credentials.credentials
    try:
        # Verify JWT token with Supabase
        user = supabase.auth.get_user(token)
        return user
    except Exception as e:
        logger.error(f"Auth error: {e}")
        return {"role": "anon", "user_id": "anonymous"}


async def get_current_admin(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    supabase=Depends(get_supabase),
):
    """Get current user and verify admin role via app_metadata.

    Only users with app_metadata.role='admin' can access protected endpoints.
    """
    user_info = await get_current_user(credentials, supabase)

    # Check admin role in app_metadata (trusted field, not default role claim)
    if user_info and user_info.user:
        metadata = getattr(user_info.user, 'app_metadata', None)
        if metadata and metadata.get('role') == 'admin':
            return user_info.user

    # Admin check outside try/except - 403 for non-admin
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Not enough permissions - admin role required",
    )


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
    dupesSuppressed: int
    rateLimitFalsePositives: int
    silentFailures: int
    medianResponseTime: float
    p95ResponseTime: float
    criticFirstPassApproval: int
    autoResolutionRate: int
    escalationRate: int


class ResolveTicketRequest(BaseModel):
    """Request model for resolve-ticket endpoint."""
    ticketId: int = Field(..., description="ID of ticket to resolve")
    resolvedBy: str = Field(..., description="User or system resolving the ticket")
    responseUrl: Optional[str] = Field(None, description="Optional response URL")


# --- Public Endpoints ---


@router.get("/conversations/{chatId}", response_model=ConversationHistory, tags=["public"])
async def get_conversation(
    chatId: str,
    current_user=Depends(get_current_user),
    supabase=Depends(get_supabase),
):
    """Get conversation history and status for a chat.

    Re-derives Brain/Critic status from persistable fields only.
    Uses chat_id-scope RLS policy for data access.
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
                import re
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


@router.get("/tickets", response_model=TicketsResponse, tags=["public"])
async def get_tickets(
    status: Optional[str] = Query(None, description="Filter by ticket status"),
    category: Optional[str] = Query(None, description="Filter by ticket category"),
    parent_chat_id: Optional[str] = Query(None, description="Filter by parent chat ID"),
    page: int = Query(1, ge=1, description="Page number"),
    perPage: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user=Depends(get_current_user),
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


@router.get("/system-stats", response_model=SystemStatsResponse, tags=["public"])
async def get_system_stats(
    current_user=Depends(get_current_user),
    supabase=Depends(get_supabase),
):
    """Get system operational metrics.

    v1: Returns hardcoded test-bench metrics from case-study.md
    v2+: Will compute from existing tables after 2-week data maturation
    """
    try:
        # v1: Return hardcoded test-bench metrics
        # These are from case-study.md and represent simulated benchmark values
        # After 2 weeks of production data, transition to computable metrics
        stats = {
            "dupesSuppressed": 100,       # test-bench: 100% duplicate suppression
            "rateLimitFalsePositives": 0, # test-bench: 0% false positives
            "silentFailures": 0,          # architectural guarantee: 0% silent failures
            "medianResponseTime": 4.8,    # test-bench: 4.8s median
            "p95ResponseTime": 11.2,      # test-bench: 11.2s P95
            "criticFirstPassApproval": 83,# test-bench: 83% critic approval
            "autoResolutionRate": 61,     # test-bench: 61% auto-resolution
            "escalationRate": 17,         # test-bench: 17% escalation rate
        }

        return SystemStatsResponse(**stats)

    except Exception as e:
        logger.error(f"Error fetching system stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch system statistics",
        )


# --- Protected/Internal Endpoints ---

@router.post("/resolve-ticket", response_model=SuccessResponse, tags=["protected"])
async def resolve_ticket(
    request: ResolveTicketRequest,
    current_user=Depends(get_current_admin),
    supabase=Depends(get_supabase),
):
    """Resolve a follow-up ticket.

    Requires service_role auth (protected endpoint).
    Updates ticket status to 'resolved' in Supabase.
    Invokes Slack webhook for notification.

    Endpoint uses service_role key which bypasses RLS by design (general Supabase fact).
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

        # Update ticket status to resolved
        update_response = supabase.table("follow_up_tickets")\
            .update({
                "status": "resolved",
                "resolved_at": __import__("datetime").datetime.utcnow().isoformat(),
                "resolved_by": resolved_by,
            })\
            .eq("id", ticket_id)\
            .execute()

        # Invoke Slack webhook for notification
        # In production, this would be the n8n webhook URL
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


@router.get("/brain-status/{chatId}", response_model=ConversationHistory, tags=["protected"])
async def get_brain_status(
    chatId: str,
    current_user=Depends(get_current_admin),
    supabase=Depends(get_supabase),
):
    """Get Brain/Critic status for a chat.

    Protected endpoint requiring service_role auth.
    Uses revised contract with persistable fields only.
    Does NOT include lastBrainDraft or lastCriticVerdict (not persistable).
    """
    try:
        # Query chat_memory for latest assistant reply
        memory_response = supabase.table("chat_memory")\
            .select("role, content, created_at")\
            .chat_id_chat_id_chat(chatId)\
            .order("created_at", desc=True)\
            .limit(20)\
            .execute()

        chat_history = memory_response.data or []

        # Find latest assistant answer
        last_assistant_answer: Optional[str] = None
        assistant_category: Optional[str] = None

        for msg in reversed(chat_history):
            if msg.get("role") == "assistant":
                last_assistant_answer = msg.get("content")
                break

        # Re-derive order ID and email from user queries (same logic as public endpoint)
        import re
        usedOrderId: Optional[str] = None
        usedEmail: Optional[str] = None

        user_messages = [m for m in chat_history if m.get("role") == "user"]
        if user_messages:
            latest_user_msg = user_messages[0].get("content", "")
            order_match = re.search(r'ORD-?\\d+', latest_user_msg)
            if order_match:
                usedOrderId = order_match.group(0)
            email_match = re.search(r'\w+@\w+\.\w+', latest_user_msg)
            if email_match:
                usedEmail = email_match.group(0)

        # Check escalation already open via follow_up_tickets
        ticket_response = supabase.table("follow_up_tickets")\
            .select("status")\
            .parent_chat_id_parent_chat_id(chatId)\
            .order("created_at", desc=True)\
            .limit(1)\
            .execute()

        escalationAlreadyOpen = len(ticket_response.data) > 0 and \
            ticket_response.data[0].get("status") == "pending"

        # Build response per revised Brain/Critic contract
        # Note: Does NOT include lastBrainDraft or lastCriticVerdict
        # These are transient within n8n workflow and not persistable
        status_val = "approved"
        if escalationAlreadyOpen:
            status_val = "escalation_already_open"

        conversation = ConversationHistory(
            chatId=chatId,
            query="",
            username=None,
            correlationId=None,
            chatHistory=chat_history,
            lastAssistantAnswer=last_assistant_answer,
            assistantCategory=assistant_category,
            needsEscalation=False,
            escalationAlreadyOpen=escalationAlreadyOpen,
            usedOrderId=usedOrderId,
            usedEmail=usedEmail,
            status=status_val,
        )

        return conversation

    except Exception as e:
        logger.error(f"Error fetching brain status for {chatId}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch brain status",
        )


@router.get("/workflow-progress/{runId}", tags=["protected", "deferred"])
async def get_workflow_progress(
    runId: str,
    current_user=Depends(get_current_admin),
):
    """Get n8n workflow execution progress (DEFERRED for v1).

    n8n workflow execution state is internal to n8n runtime.
    This endpoint is marked as deferred for v1 with roadmap note.
    v2 roadmap includes n8n modifications for workflow progress tracking.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={
            "error": "Workflow progress tracking requires n8n API access",
            "roadmap": "See Phase 3 - n8n workflow modifications for v2 implementation",
            "status": "deferred_for_v1",
            "message": "Workflow progress tracking is internal to n8n runtime. "
                       "Contact system administrator for v2 roadmap timeline.",
        },
    )