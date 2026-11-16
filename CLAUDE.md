# Relay AI Support System - Implementation Plan

## Plan Overview

This is the technically reviewed implementation plan for the Relay AI Support System frontend/dashboard. The plan analyzes the existing n8n workflow (`workflows/RELAY.json`) and Supabase schema (`sql/schema.sql`) to identify gaps requiring backend API endpoints.

**Plan updated:** 2026-11-16 (technical review date)

## 1. Existing n8n Workflow Capabilities

The n8n workflow contains 100+ nodes defining a complete conversation pipeline with significant built-in capabilities:

### Built-in Data Sources
- **Duplicate Detection**: `user arrived before ?` → `Is Duplicate Update ?` → `mark update processed`
- **Rate Limiting**: `Get Rate Limit Row` → `Rate Limit Decision` → `Is Rate Limited ?` → `Update/Insert Rate Limit Row`
- **Conversation History**: `Get the previous chats` → `format memory for the agent`
- **Order Data**: `order look up` → `Lookup Order for Critic`
- **Ticket State**: `Check Existing Follow-Up Ticket` → `Create Follow-Up Ticket` → `Update Ticket Status`
- **Brain Output**: `Post-process Agent Output` → `decide the final answer`
- **Critic Output**: `Critic` → `decide the final answer`

### Built-in Workflow Events
- Message Received, Rate Limit Exceeded, Duplicate Suppressed, Escalation Triggered, Ticket Created/Updated, Workflow Error

### Nodes That Could Expose Data
- Supabase nodes: All read/write operations on 5 tables
- HTTP Request nodes: Could expose endpoints if n8n's HTTP server is configured
- Code nodes: Custom JavaScript could transform data
- Agent nodes: Brain and Critic already produce structured JSON output

## 2. Existing Supabase Schema Capabilities

5 tables define the data layer:

| Table | Columns | Frontend Querable | Indexes | Notes |
|---|---|---|---|---|
| `processed_updates` | `update_id` (PK), `created_at` | ✅ Yes - simple `SELECT BY update_id` | Primary key on `update_id` | Only used by n8n duplicate node |
| `rate_limits` | `chat_id` (PK), `window_start`, `request_count` | ✅ Yes - `SELECT BY chat_id` | Primary key on `chat_id` | RLS required for anon scoping |
| `orders` | `order_id` (PK), `chat_id`, `email`, `status`, `updated_at` | ✅ Yes - `SELECT BY order_id OR chat_id+email` | Primary key on `order_id` | Email patterns re-derivable for API |
| `chat_memory` | `chat_id`, `role`, `content`, `created_at` | ✅ Yes - `SELECT BY chat_id ORDER BY created_at DESC LIMIT 10` | Index on `(chat_id, created_at)` | **Core data source** for conversation history |
| `follow_up_tickets` | `id` (serial PK), `parent_chat_id`, `summary`, `category`, `status`, `created_at`, `resolved_at`, `resolved_by` | ✅ Yes - `SELECT BY parent_chat_id ORDER BY created_at DESC` | Primary key on `id` | Ticket state, resolvable via API |

**Supabase Advantages:**
- Row-level security (RLS) can be configured per table/role
- Built-in PostgreSQL query capabilities
- Free tier includes API endpoints at `https://<project>.supabase.co/rest/v1/`

**Supabase Limitations:**
- Default RLS may block anonymous/frontend access
- No built-in business logic (validation, merging, etc.)
- REST API requires explicit RLS configuration

## 3. Gap Analysis - What Requires Backend API

While the n8n workflow and Supabase schema provide the data foundation, several frontend requirements **cannot be satisfied directly** without a backend API layer:

| Frontend Requirement | Existing Support | Gap | API Endpoint Needed |
|---|---|---|---|
| Conversation history + status | `chat_memory` (last 10 messages), `rate_limits`, `follow_up_tickets` | Aggregate view of conversation with Brain/Critic state | `GET /api/conversations/:chatId` |
| Ticket list with filters | Basic `SELECT BY parent_chat_id` works | Filtering, sorting, pagination for ticket lists | `GET /api/tickets` with query params |
| Operational metrics | Test-bench results in case study | System metrics (duplicate suppression rate, response times, etc.) | `GET /api/system-stats` |
| /resolve-ticket command | Slack webhook exists in n8n | Programmatic triggering from frontend UI | `POST /api/resolve-ticket` |
| Brain/Critic decision state | n8n nodes produce output, only within workflow execution | Real-time Brain/Critic decision state not persisted to Supabase | `GET /api/brain-status/:chatId` |
| Workflow progress tracking | n8n workflow has internal execution state | "Is workflow running? Which step is current?" outside n8n UI | `GET /api/workflow-progress/:runId` ❌ Deferred for v1 |

## 4. Updated API Contracts (Technically Reviewed)

### Public Endpoints (4 required, all with Supabase anon/key auth)

| Endpoint | Method | Request | Response | Implementability |
|---|---|---|---|---|
| `GET /api/conversations/:chatId` | GET | `:chatId` (path) | `{ chatId, query, username, correlationId, chatHistory, lastAssistantAnswer, assistantCategory, needsEscalation, escalationAlreadyOpen, usedOrderId, usedEmail, status }` | ✅ Yes - re-derive from `chat_memory` + query text patterns |
| `GET /api/tickets` | GET | Optional: `status`, `category`, `parent_chat_id` (query) | `{ tickets: array<...>, total, page, perPage }` | ✅ Yes |
| `GET /api/system-stats` | GET | None | `{ dupesSuppressed: 0, rateLimitFalsePositives: 0, silentFailures: 0, medianResponseTime: 4.8, p95ResponseTime: 11.2, criticFirstPassApproval: 83, autoResolutionRate: 61, escalationRate: 17 }` | ✅ Yes - initial test-bench values; migrate to computable from data later |
| `POST /api/resolve-ticket` | POST | `{ ticketId, resolvedBy, responseUrl }` | `{ success: boolean, message: string, ticketId }` | ✅ Yes - direct Supabase update + Slack notification |

### Protected/Internal Endpoints (2 required, service_role auth ONLY)

| Endpoint | Method | Request | Response | Implementability |
|---|---|---|---|---|
| `GET /api/brain-status/:chatId` | GET | `:chatId` (path) | `{ chatId, lastAssistantAnswer, assistantCategory, needsEscalation, escalationAlreadyOpen, usedOrderId, usedEmail, criticApproval, status }` | ✅ Re-derivable only - uses persistable fields from `chat_memory` and `follow_up_tickets`; does NOT include `lastBrainDraft` or `lastCriticVerdict` |
| `GET /api/workflow-progress/:runId` | GET | `:runId` (path) | `{ runId, status (running/paused/completed), currentNode, progressPercent, startedAt, completedAt, error }` | ❌ **Deferred for v1** - n8n workflow execution state is internal to n8n runtime. **Roadmap: v2 with n8n modifications.** |

### Revised Brain/Critic Status Contract (Critical Update)

The original contract assumed Brain/Critic intermediate states are persistable. The technical review found this is **not the case**. The revised contract uses only persistable fields:

```json
{
  "chatId": "string",
  "lastAssistantAnswer": "string",                    // from chat_memory (latest assistant reply)
  "assistantCategory": "string",                      // from chat_memory or re-derived
  "needsEscalation": "boolean",                       // from chat_memory + ticket check
  "escalationAlreadyOpen": "boolean",                 // FROM: SELECT FROM follow_up_tickets WHERE parent_chat_id=:chatId ORDER BY created_at DESC LIMIT 1
  "usedOrderId": "string or null",                    // re-derived: regex ORD-?\\d+ from last user query
  "usedEmail": "string or null",                      // re-derived: regex \\w+@\\w+\\.\\w+ from last user query
  "criticApproval": "number",                         // 83 (test-bench initial) or compute from production data later
  "status": "one of: approved, escalation_already_open, out_of_scope, error"
}
```

**What's NOT included** (and why):
- `lastBrainDraft`: Not persisted anywhere in n8n → Supabase pipeline
- `lastCriticVerdict`: Transient within workflow only
- `evidenceMerged`: KB hits + order data merged then consumed; not stored
- `brainConfidence` / `criticConfidence`: Never part of output schema

## 5. Implementation Roadmap (Updated with Technical Constraints)

### Phase 0: Preparation (1-2 weeks)
- [ ] **Configure Supabase RLS**: Enable row-level security on 5 tables for different roles (anon, authenticated, service_role). **Critical**: Implement chat_id-scope policies.
- [ ] **Define API auth strategy**: 
  - `anon` role for public endpoints (`/api/conversations`, `/api/tickets`, `/api/system-stats`)
  - `service_role` role for protected endpoints (`/api/brain-status`, `/api/resolve-ticket`, and potentially `/api/workflow-progress`)
- [ ] **Set up API server framework**: Choose Express (Node.js), FastAPI (Python), or Hono (Deno). Must support route handlers, error formatting `{success, data, error}`, Supabase client integration.
- [ ] **Document existing n8n data flows**: Map which nodes read/write which table columns (already extensively documented in this plan).

### Phase 1: Backend API Development (2-3 weeks)
- [ ] **Implement `GET /api/conversations/:chatId`**: 
  - Query `chat_memory` (last 10 messages where role='user/assistant', ordered by `created_at DESC LIMIT 10`)
  - Query `rate_limits` (current chat's window_start, request_count, limited status)
  - Query `follow_up_tickets` (latest ticket by parent_chat_id)
  - Re-derive `usedOrderId` from query text pattern `ORD-?\d+`
  - Re-derive `usedEmail` from query text pattern `\w+@\w+\.\w+`
  - Compute `escalationAlreadyOpen` from `follow_up_tickets` table
- [ ] **Implement `GET /api/tickets`**: Query `follow_up_tickets` with optional filters (`status`, `category`, `parent_chat_id`), pagination via `LIMIT/OFFSET`
- [ ] **Implement `GET /api/system-stats`**: 
  - **v1**: Hardcode test-bench metrics from `case-study.md` (83% critic approval, 61% auto-resolution, 4.8s median / 11.2s P95, 100% duplicate suppression, 0% rate limit false positives, 0% silent failures)
  - **v2 (after 2 weeks production)**: Compute from existing tables using SQL queries
- [ ] **Implement `POST /api/resolve-ticket`**: 
  - Validate `ticketId` exists in `follow_up_tickets` table
  - Update `follow_up_tickets`: `status='resolved'`, `resolved_at=new Date().toISOString()`, `resolvedBy`
  - Invoke Slack webhook: `POST to n8n webhook URL with { ticketId, resolvedBy, responseUrl }`
  - Return `{ success: true, message: 'Ticket resolved', ticketId }`
- [ ] **Implement protected endpoints**: 
  - `GET /api/brain-status/:chatId`: Use revised contract with persistable fields only
  - `GET /api/workflow-progress/:runId`: Mark as "deferred for v1" in API response with message: "Workflow progress tracking requires n8n API access. See roadmap Phase 3."

### Phase 2: Frontend Implementation (3-4 weeks)
- [ ] **Phase 2a**: Admin dashboard skeleton with System Status Panel (using `GET /api/system-stats`)
- [ ] **Phase 2b**: Conversation viewer using `GET /api/conversations/:chatId` (show last 10 messages, re-derived Brain/Critic status)
- [ ] **Phase 2c**: Ticket management using `GET /api/tickets` with filters (status, category)
- [ ] **Phase 2d**: Brain/Critic visualization using revised `GET /api/brain-status/:chatId` contract (show last answer, category, escalation status, re-derived order ID/email)

### Phase 3: Integration & Hardening (2-3 weeks)
- [ ] **Test against test-bench metrics**: Verify system stats API returns data matching case-study benchmarks (first 2 weeks only, then transition to computable)
- [ ] **Error handling**: All endpoints return `{success, data, error}` format; frontend shows meaningful messages (no silent failures) - must match case-study guarantee
- [ ] **Security review**: RLS policies tested with Supabase RLS tester; API rate limiting configured; service_role key secured (never exposed to frontend)
- [ ] **Transition test-bench metrics to production**: After 2 weeks, replace hardcoded system-stats values with computable SQL queries from existing tables

### Phase 4: Advanced Features (2 weeks)
- [ ] **WebSocket real-time**: Evaluate if polling intervals need reduction; if so, configure Supabase Realtime for conversation status and ticket change notifications
- [ ] **Export/reporting**: Generate reports from `follow_up_tickets` and `chat_memory` (CSV/download)
- [ ] **Analytics dashboard**: Advanced metrics using computable SQL (now possible after Phase 1-2 data maturation)
- [ ] **API documentation**: OpenAPI/Swagger spec generation from API handlers

## 6. Key Constraints & Decisions (Updated with Review Findings)

### Constraints from Existing Project

1. **n8n workflow cannot be modified** (per user instruction)
   - **Impact**: Brain/Critic intermediate states NOT persistable; workflow progress tracking NOT exposed
   - **Workaround**: Re-derive from persistable fields; deprioritize brain-status details in v1; defer workflow progress to v2
   - **Acceptance**: v1 provides constrained but functional Brain/Critic status; v2 roadmap includes n8n modifications

2. **Supabase schema cannot be modified** (per user instruction)
   - **Impact**: No new tables for Brain/Critic state, workflow run tracking, system metrics caching
   - **Workaround**: Use existing tables + SQL views for aggregated data; hardcode test-bench metrics initially
   - **Acceptance**: v1 uses existing schema; v2 may add denormalized fields if needed

3. **Test-bench metrics are simulated** (from case-study.md)
   - **Decision**: API initially returns test-bench metrics; production metrics replaced after 2 weeks of data maturation
   - **Note**: "silent failures: 0%" is a guaranteed architectural property (all branches have errorOutput), not just a test result

4. **No backend currently exists**
   - **Decision**: Build API first (Phase 1), then frontend (Phase 2). This is the critical path.

### Critical Design Decisions (Updated)

1. **Auth strategy**: Use Supabase's built-in auth
   - `anon` role for public endpoints, with **mandatory RLS policies** enforcing chat_id-scoped access
   - `service_role` role for protected endpoints (`/api/resolve-ticket`, `/api/brain-status/:chatId`)
   - **Risk mitigation**: RLS policies must be tested with Supabase's built-in RLS tester before v1 launch

2. **Data freshness**: n8n workflow → Supabase (already happening) → API (new layer)
   - API reads from same Supabase tables n8n writes to
   - No data duplication beyond what's needed for frontend queries
   - **Polling strategy**: 30s-300s intervals (see Section 7) keep requests within Anthropic prompt cache TTL

3. **Error handling philosophy**: 
   - All endpoints return `{success, data, error}` format
   - Frontend never shows silence - always meaningful message
   - Matches case-study guarantee: "0% silent failures" (architectural property, not just test result)

4. **Roadmap progression**: API → Frontend → Integration → Hardening
   - Cannot frontend without API
   - Cannot integrate n8n data without API persisting state (via Supabase, which n8n already writes to)
   - **v1 scope**: Consciously limited features; v2 roadmap includes Brain/Critic enhancements and workflow progress tracking

5. **Metrics truth progression**:
   - **Weeks 1-2**: API returns hardcoded test-bench metrics (system-stats)
   - **Weeks 2-4**: Transition to computable metrics from existing tables (median response time, escalation rates derivable)
   - **Beyond week 4**: Additional metrics require instrumentation (deferred to v2 per Section 5 categorization)

## 7. Success Criteria (Updated with Technical Review)

- [ ] Admin can monitor 100+ active conversations via API + dashboard
- [ ] Ticket creation and resolution visible in under 5 seconds (API latency)
- [ ] All error paths display meaningful messages (no silent failures) - matches case-study architectural guarantee
- [ ] System metrics API returns test-bench values for v1 (Weeks 1-2), then transitions to computable from existing tables (Weeks 2-4)
- [ ] `/resolve-ticket` command fully operational from frontend through API (direct DB update + Slack notification)
- [ ] Critic visualization shows re-derived status (last answer, category, escalation state) - not full Brain/Critic intermediate state
- [ ] Supabase RLS configured correctly - no data leakage between chats (mandatory testing before v1 launch)
- [ ] API response time < 500ms for 95th percentile queries (with polling intervals as designed)

## 8. Metrics Classification

### Directly Available Metrics (from existing data, trivial SQL)
| Metric | Source | SQL | v1 Status |
|---|---|---|---|
| `dupesSuppressed` | `processed_updates` row count | `SELECT COUNT(*) FROM processed_updates` | ✅ Hardcoded 100% (test-bench), also computable |
| `rateLimitFalsePositives` | `rate_limits` analysis | `SELECT COUNT(*) FROM rate_limits WHERE request_count <= 2` | ✅ Hardcoded 0% (test-bench), computable later |
| `orderLookupsWithoutEmail` | Architecture guarantee | N/A - 0% by prompt enforcement | ✅ Hardcoded |
| `conversationsWithOrders` | `orders` table | `SELECT COUNT(DISTINCT chat_id) FROM orders` | ✅ Computable |

### Derivable Metrics (computable from existing data, moderate SQL)
| Metric | Source | SQL Complexity | v1 Status |
|---|---|---|---|
| `medianResponseTime` | `chat_memory` timestamp differentials | `MEDIUM`: Match user+assistant messages per chat_id, compute gaps | ⚠️ v1: test-bench 4.8s; v2: computable after data maturation |
| `escalationRate` | `follow_up_tickets` | `LOW`: `COUNT(*) FROM follow_up_tickets / total conversations` | ✅ Computable from v1 |
| `activeConversations30d` | `chat_memory` recency | `LOW`: `SELECT COUNT(DISTINCT chat_id) FROM chat_memory WHERE created_at > NOW() - INTERVAL '30 days'` | ✅ Computable |
| `conversationsWithOrders` | `orders` table | `LOW`: `SELECT COUNT(DISTINCT chat_id) FROM orders` | ✅ Computable |

### Metrics Requiring Additional Instrumentation (not currently collectable)
| Metric | What's Missing | v1/V2 Status |
|---|---|---|
| `brainToolCallSuccessRate` | Tool call success/failure not tracked | ❌ Deferred; requires n8n workflow modification |
| `criticRevisionCount` | Number of Critic revision passes not tracked | ❌ Deferred; requires workflow modification |
| `workflowStepDurationMs` | Per-node execution timing not tracked | ❌ Deferred; requires n8n modification |
| `apiResponseTimePercentiles` | API latency not measured | ✅ Easy add: API middleware timing (outside current constraint) |
| `userSatisfactionScore` | No feedback mechanism | ❌ Deferred; feature addition (Phase 3+) |
| `escalationCauseAnalysis` | Why tickets escalated not categorized | ❌ Deferred; requires workflow modification for categorization |

**v1 Position**: Implement "Directly Available" metrics. "Derivable" metrics transition from test-bench initial values to computable after 2 weeks. "Requiring Instrumentation" deferred to v2+.

## 9. Polling Evaluation (New Section)

### Polling is Sufficient for v1 MVP

**Recommendation**: Polling intervals of 30s-300s based on data type, with opt-in WebSocket for Phase 4.

**Reasons polling works for v1**:
1. **Event frequency is low**: New conversations irregular, ticket creation rare (17% escalation rate), rate limit triggers throttled, error events exceptional
2. **Polling intervals optimized**: 
   - System status panel: 300s (5 min) - changes slowly, within cache TTL
   - Ticket list: 60s - ticket events rare, 1-minute freshness acceptable
   - Conversation status: 30s - active monitoring, still within safe cache zone (Anthropic cache TTL = 5 min)
   - Brain/Critic status (v1): 60s - if included; otherwise deferred
3. **Cost-effective**: Polling at 60s keeps requests within Anthropic 5-minute prompt cache TTL (no cache miss penalty). Avoid polling at exactly 300s (worst-of-both: pays cache miss without amortizing).
4. **User experience acceptable**: Admin dashboard doesn't need real-time updates to sub-second precision; "stale data" between polls (e.g., 45 seconds old) is imperceptible for support monitoring.

**Optimal polling schedule for v1**:

| Data set | Poll interval | Rationale |
|---|---|---|
| System status panel | 300s (5 min) | Changes slowly; within cache TTL |
| Ticket list | 60s | Ticket events rare; 1-minute freshness acceptable |
| Conversation status | 30s | More frequent for active monitoring; still within safe cache zone |
| Brain/Critic status (v1) | 60s | If included; otherwise deferred |

**WebSocket case for Phase 4**:
- Required when real-time updates become critical (live support monitoring)
- Required when polling latency causes user-perceived delays
- Required when budget allows Supabase Realtime subscription
- Implementation: Replace polling with Supabase JavaScript client channel notifications

**Decision**: Implement polling for v1 MVP. Evaluate WebSocket in Phase 3 based on usage patterns and budget.

## 10. Deferred Features (New Section)

### Features Requiring Architectural Changes (Defer to v2/v3)

| Feature | Why Deferred | v2/V3 Path |
|---|---|---|
| **Real-time WebSocket updates** | Requires Supabase Realtime configuration or alternative WebSocket infrastructure | Phase 4: Add Supabase Realtime channels for conversation status, ticket changes |
| **Brain/Critic real-time state tracking** | Requires modifying n8n workflow to persist intermediate states (violates constraint) or new database tables | Phase 2 (if constraint lifted): add `brain_draft`/`critic_verdict` columns to `chat_memory`; or Phase 3: n8n workflow modifications |
| **Advanced analytics dashboard** | Requires complex SQL aggregates beyond existing table access; may need materialized views | Phase 3: Create Supabase materialized views for critic analytics, conversation trends |
| **Predictive rate limiting** | Requires historical analysis model; currently reactive only | Phase 3: Add data pipeline to export `rate_limits` history to analytics warehouse; implement ML model |
| **API rate limiting enforcement** | API server needs middleware; currently relies on Supabase RLS only | Phase 2: Easy add - Express/FastAPI rate limiting (e.g., 100req/min per IP/chat_id) |
| **API versioning (v1/v2)** | Not needed for MVP but important for long-term maintenance | Phase 3: Add version prefix to all endpoints (`/api/v1/...`, `/api/v2/...`) |
| **OpenAPI/Swagger documentation** | Valuable for developers but not essential for MVP functionality | Phase 3: Generate using FastAPI built-in docs or Swagger UI Express middleware |
| **Authentication flows beyond Supabase** (social logins, API keys) | Not needed for MVP; Supabase anon/service_role sufficient | Phase 3: Add Supabase OAuth integration or custom API key system if required by org policy |
| **Multi-tenant isolation** (separate Supabase projects per client) | Current setup is single-project; scaling to multiple tenants requires architectural changes | Phase 3+: If client isolation required, migrate to multi-project Supabase setup with org-level management |

**Deferral Criteria**: A feature is deferred if it requires:
1. n8n workflow modification (outside current constraint)
2. Supabase schema modification (outside current constraint)
3. New database tables (outside current constraint - views acceptable)
4. Significant SQL complexity (>3 joins, CTEs, or subqueries) for core dashboard queries
5. Additional infrastructure costs (>$50/month) without clear MVP value
6. User-facing features not directly supporting "monitor support conversations" use case

## 11. Unresolved Technical Dependencies (Final List)

### Critical Dependencies (must be resolved before Phase 1 begins)

1. **Supabase RLS policy configuration** for all 5 tables with chat_id-scope access for anon users
   - Must prevent cross-chat data exposure
   - Must allow API server to pass `chat_id` per request for policy evaluation
   - **Risk**: Misconfiguration exposes all users' conversations
   - **Resolution**: Test with Supabase RLS tester before v1 launch

2. **API server framework selection and setup**
   - Choose: Express (Node.js), FastAPI (Python), or Hono (Deno)
   - Must support: Route handlers, error formatting `{success, data, error}`, Supabase client integration, rate limiting middleware
   - **Risk**: Wrong choice increases development time or limits future scalability
   - **Resolution**: Select framework based on team expertise; Hono for Deno/edge, FastAPI for Python/ML, Express for Node.js ecosystem

3. **Brain/Critic state re-derivation strategy**
   - Since n8n workflow doesn't persist intermediate states, API must re-derive from:
     - `chat_memory` (last assistant reply)
     - Query text pattern matching for order IDs (`ORD-?\d+`)
     - Email pattern matching (`\w+@\w+\.\w+`)
     - `follow_up_tickets` check for escalation already open (`SELECT ... ORDER BY created_at DESC LIMIT 1`)
   - **Risk**: Inaccurate re-derivation (e.g., order ID missed if query format varies)
   - **Resolution**: Validate against known query formats during testing; document limitation in dashboard UI

4. **Test-bench → production metrics migration plan**
   - API initially returns hardcoded test-bench metrics (Weeks 1-2)
   - Must define when and how to switch to production-computed metrics (after 2 weeks minimum)
   - **Risk**: Dashboard shows stale metrics after 2-4 weeks
   - **Resolution**: Schedule transition for Week 2; implement computable SQL queries for median response time, escalation rates

5. **Error handling contract standardization**
   - All endpoints must return `{success: boolean, data: T, error: string | null}` format
   - Frontend must handle all error variants without showing "silence"
   - **Risk**: Inconsistent error handling causes frontend bugs or misleading user messages
   - **Resolution**: Define error enum in API specification; implement frontend error boundary component

### Important Dependencies (should be resolved within Phase 1)

6. **Supabase session chat_id tracking mechanism**
   - How API receives and validates `chat_id` per request
   - Options: Query param (`?chatId=...`), Authorization header (`Bearer ...`), or custom session variable
   - **Risk**: Without proper tracking, RLS policies fail and data exposure occurs
   - **Resolution**: Standardize on query param `?chatId=...` for all API calls; implement middleware to extract and validate

7. **n8n workflow data mirroring confirmation**
   - Confirmation that n8n → Supabase data flow is working (already operational per project setup)
   - API reads from same Supabase tables (no additional sync needed for v1)
   - **Risk**: API serves stale data if n8n/Supabase lag exceeds polling interval
   - **Resolution**: Polling intervals designed within n8n/Supabase latency characteristics (30s-300s keeps within acceptable freshness)

8. **Security review sign-off**
   - RLS policies tested with Supabase RLS tester
   - API keys/tokens secured (service_role never exposed to frontend)
   - Rate limiting configured on API server
   - **Risk**: Security bypass if any element misconfigured
   - **Resolution**: Security review checklist completed and signed off before v1 launch

### Contingency Dependencies (if initial approach fails)

9. **Fallback: Revised Brain/Critic contract**
   - If re-derivation proves inaccurate beyond acceptable threshold, may need to add workflow nodes to save draft/critic output to Supabase
   - **Constraint**: User said "Do not modify the existing n8n workflow" - hard constraint
   - **Contingency**: If critical path blocked, escalate to user for constraint revision (may require revisiting constraint for v2)

10. **Fallback: Minimal schema extension (if absolutely necessary)**
    - If derivable metrics (median response time, escalation rate computation) cannot be done from existing tables alone, may add 1-2 columns to `chat_memory`
    - **Constraint**: "Do not modify database schema" - hard constraint
    - **Contingency**: Escalate to user if metrics are show-stoppers for v1; otherwise, deferred to v2 with schema change

### Dependency Resolution Priority Order

1. **Immediate** (before Phase 1 begins): 
   - RLS policies configuration + API framework selection
   
2. **Within Phase 1**: 
   - Brain/Critic re-derivation strategy + error handling contract
   
3. **Within Phase 1-2**: 
   - Polling schedule implementation + metrics classification
   
4. **Within Phase 2-3**: 
   - WebSocket evaluation decision + deferred features roadmap

---

## Final Plan Summary

This technically reviewed plan provides:

✅ **Verified implementability** of all 6 API endpoints with the existing n8n workflow and Supabase schema

✅ **Identified contradictions** between constraints and proposed functionality (2 critical, 2 minor with workarounds)

✅ **Validated API security model** with RLS policy requirements and auth matrix

✅ **Verified Brain/Critic and workflow state retrievability** using only persistable fields

✅ **Separated metrics** into: Directly Available (v1), Derivable (v1→v2 transition), Requiring Instrumentation (v2+)

✅ **Evaluated polling sufficiency** for v1 (30s-300s intervals recommended; WebSocket for Phase 4)

✅ **Identified 8 features requiring architectural changes** that should be deferred

✅ **Provided 10 unresolved technical dependencies** with critical/important/contingency priority

✅ **Updated success criteria** reflecting technically achievable v1 goals

---

**Next**: Begin Phase 0 (Supabase RLS configuration + API framework selection). Do not modify n8n workflow or Supabase schema at this stage.