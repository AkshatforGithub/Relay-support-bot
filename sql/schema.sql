-- =============================================================================
-- Relay: Supabase / Postgres schema
-- Run once in the Supabase SQL editor (or: psql "$DATABASE_URL" -f sql/schema.sql)
-- Safe to re-run: tables and indexes use IF NOT EXISTS.
-- Table and column names match the Supabase nodes in the n8n workflow.
-- =============================================================================


-- processed_updates: webhook de-duplication.
-- Telegram can redeliver an update. The workflow checks this table first and
-- marks the update as processed before doing any work, so a retry can never
-- cause a duplicate reply.
create table if not exists processed_updates (
  update_id  bigint primary key,          -- Telegram update_id
  created_at timestamptz default now()
);


-- rate_limits: one row per chat.
-- The workflow reads the row, decides whether the chat is over its limit for
-- the current window, then updates or inserts the row.
create table if not exists rate_limits (
  chat_id       text primary key,
  window_start  timestamptz not null,
  request_count int not null default 1
);


-- orders: live order data for the order-lookup tool.
-- The agent needs both the order id and the customer's email before it may
-- look an order up.
create table if not exists orders (
  order_id   text primary key,
  chat_id    text not null,
  email      text,
  status     text,
  updated_at timestamptz
);


-- chat_memory: conversation memory.
-- Both sides of each conversation are saved here (one row per message). The
-- agent reads the 10 most recent messages for the chat, newest first.
create table if not exists chat_memory (
  chat_id    text not null,
  role       text not null,
  content    text not null,
  created_at timestamptz default now()
);

create index if not exists idx_chat_memory_chat
  on chat_memory (chat_id, created_at);


-- follow_up_tickets: escalation state.
-- New tickets start as 'pending'. resolved_at and resolved_by are filled in
-- when a teammate resolves the ticket from Slack with /resolve-ticket <id>.
create table if not exists follow_up_tickets (
  id             serial primary key,
  parent_chat_id text,
  summary        text,
  category       text,
  status         text default 'pending',
  created_at     timestamptz default now(),
  resolved_at    timestamptz,
  resolved_by    text
);

