"""Phase 1 — Tests for Relay AI Support System API endpoints.

Tests verify that all Phase 1 endpoints are properly structured and
can be imported without errors. Actual Supabase connectivity requires
valid credentials.
"""

import pytest
from fastapi.testclient import TestClient

# Import the app and test client
from ...main import app

client = TestClient(app)


class TestHealthEndpoint:
    """Test health check endpoint."""

    def test_health_check(self):
        """GET /health should return ok."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "relay-api"


class TestRootEndpoint:
    """Test root endpoint."""

    def test_root_endpoint(self):
        """GET / should return message."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "Relay AI Support System API" in data["message"]


class TestAPIRouterImport:
    """Test that API router can be imported."""

    def test_router_import(self):
        """API router should be importable."""
        from ...api.endpoints import router
        assert router is not None


class TestEndpointsStructure:
    """Test that endpoint functions are properly defined."""

    def test_conversation_endpoint_exists(self):
        """GET /api/conversations/{chatId} should be defined."""
        routes = [route for route in app.routes if hasattr(route, 'path')]
        conversation_routes = [r for r in routes if "/conversations" in str(r.path)]
        assert len(conversation_routes) > 0

    def test_tickets_endpoint_exists(self):
        """GET /api/tickets should be defined."""
        routes = [route for route in app.routes if hasattr(route, 'path')]
        ticket_routes = [r for r in routes if "/tickets" in str(r.path)]
        assert len(ticket_routes) > 0

    def test_system_stats_endpoint_exists(self):
        """GET /api/system-stats should be defined."""
        routes = [route for route in app.routes if hasattr(route, 'path')]
        stats_routes = [r for r in routes if "/system-stats" in str(r.path)]
        assert len(stats_routes) > 0

    def test_resolve_ticket_endpoint_exists(self):
        """POST /api/resolve-ticket should be defined."""
        routes = [route for route in app.routes if hasattr(route, 'path')]
        resolve_routes = [r for r in routes if "/resolve-ticket" in str(r.path)]
        assert len(resolve_routes) > 0

    def test_brain_status_endpoint_exists(self):
        """GET /api/brain-status/{chatId} should be defined."""
        routes = [route for route in app.routes if hasattr(route, 'path')]
        brain_routes = [r for r in routes if "/brain-status" in str(r.path)]
        assert len(brain_routes) > 0

    def test_workflow_progress_endpoint_exists(self):
        """GET /api/workflow-progress/{runId} should be defined (deferred)."""
        routes = [route for route in app.routes if hasattr(route, 'path')]
        workflow_routes = [r for r in routes if "/workflow-progress" in str(r.path)]
        assert len(workflow_routes) > 0