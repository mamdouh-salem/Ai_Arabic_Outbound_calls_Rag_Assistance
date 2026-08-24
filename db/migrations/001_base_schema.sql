-- =============================================================================
-- Migration 001: Base schema (customers, tickets, calls, knowledge_base_chunks)
--
-- These tables were originally created directly in the Supabase Dashboard and
-- never versioned in the repo. This file reconstructs them EXACTLY as they
-- exist in the live database (introspected 2026-08-23), so a fresh Supabase
-- project can be rebuilt from migrations alone.
--
-- Idempotent: safe to run on an existing project (everything is IF NOT EXISTS
-- / OR REPLACE / conditional).
--
-- Migration order for a FRESH project:
--   001_base_schema.sql        <- this file
--   002_match_chunks_768.sql   (HISTORICAL — superseded: its ivfflat index is
--                               replaced by the hnsw index here, and its
--                               match_chunks() is replaced by 003's
--                               workspace-aware version. Safe to skip.)
--   003_multi_tenancy.sql      (workspaces / users / workspace_members + RLS
--                               + workspace_id columns on the tables above)
--   004_ticket_assignment.sql, 005_call_reporting_fields.sql,
--   006_call_status.sql
--
-- NOTE: this file intentionally does NOT create the workspace_id columns or
--   their foreign keys — migration 003 owns those, keeping the original
--   single-tenant → multi-tenant evolution intact.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 0. Extensions
-- ---------------------------------------------------------------------------
create extension if not exists "uuid-ossp";     -- uuid_generate_v4()
create extension if not exists pgcrypto;        -- gen_random_uuid()
create extension if not exists vector;          -- pgvector embeddings

-- ---------------------------------------------------------------------------
-- 1. customers
-- ---------------------------------------------------------------------------
create table if not exists customers (
    id           uuid primary key default uuid_generate_v4(),
    name         text not null,
    phone        text not null unique,   -- trial note: temporarily dropped in dev
                                          -- so all calls ring one test number
                                          -- (alter table customers drop
                                          --  constraint customers_phone_key)
    created_at   timestamptz default current_timestamp
);

-- ---------------------------------------------------------------------------
-- 2. tickets
-- ---------------------------------------------------------------------------
create table if not exists tickets (
    id           uuid primary key default uuid_generate_v4(),
    customer_id  uuid references customers (id) on delete cascade,
    title        text not null,
    description  text,
    status       text not null default 'open',
    kb_category  text,
    created_at   timestamptz default current_timestamp,
    updated_at   timestamptz default current_timestamp
);

-- ---------------------------------------------------------------------------
-- 3. calls
-- ---------------------------------------------------------------------------
create table if not exists calls (
    id                uuid primary key default gen_random_uuid(),
    ticket_id         uuid references tickets (id) on delete set null,
    customer_id       uuid references customers (id) on delete set null,
    vonage_call_id    text,
    transcript        text,
    intent            text,
    kb_answer         text,
    kb_sources        jsonb,
    kb_answer_given   boolean default false,
    escalated         boolean default false,
    escalation_reason text,
    call_outcome      text,          -- resolved | escalated | unresolved
    call_summary      text,
    created_at        timestamptz default now()
);

-- ---------------------------------------------------------------------------
-- 4. knowledge_base_chunks (RAG store)
-- ---------------------------------------------------------------------------
create table if not exists knowledge_base_chunks (
    id          uuid primary key default uuid_generate_v4(),
    content     text not null,
    embedding   vector(768),         -- sentence-transformers multilingual mpnet
    metadata    jsonb default '{}'::jsonb,   -- {"source": ..., "category": ...}
    fts_tokens  tsvector,            -- kept in sync by the trigger below
    created_at  timestamptz default current_timestamp
);

-- Arabic full-text search kept in sync automatically on every write
create or replace function public.kb_chunks_tsvector_trigger()
returns trigger
language plpgsql
as $function$
begin
    new.fts_tokens := to_tsvector('arabic', coalesce(new.content, ''));
    return new;
end;
$function$;

drop trigger if exists tsvectorupdate on knowledge_base_chunks;
create trigger tsvectorupdate
    before insert or update on knowledge_base_chunks
    for each row execute function public.kb_chunks_tsvector_trigger();

-- ---------------------------------------------------------------------------
-- 5. Indexes (as in the live database)
-- ---------------------------------------------------------------------------
create index if not exists kb_chunks_fts_idx
    on knowledge_base_chunks using gin (fts_tokens);

-- hnsw outperforms the historical ivfflat index (see 002) for this corpus
create index if not exists idx_kb_chunks_embedding
    on knowledge_base_chunks using hnsw (embedding vector_cosine_ops);

create index if not exists idx_calls_ticket
    on calls (ticket_id);
create index if not exists idx_calls_created
    on calls (created_at desc);
