-- =============================================================================
-- Migration 003: Multi-Tenancy Foundation  (Supabase SQL Editor compatible)
-- Run in Supabase SQL Editor as the default postgres role.
--
-- CHANGES vs original:
--   • auth.is_super_admin()  → public.is_super_admin()   (auth schema is read-only)
--   • auth.my_workspace_ids() → public.my_workspace_ids() (auth schema is read-only)
--   • All RLS policies call public.* helpers instead of auth.*
--   • Trigger on auth.users REMOVED — Supabase SQL Editor cannot modify auth schema DDL.
--     Auto-profile creation is handled via Supabase Dashboard Auth Hook instead.
--     See "Manual Step" section at the bottom of this file.
--   • FK to auth.users REMOVED — the SQL Editor's postgres role has no DDL
--     privileges on the auth schema, so "references auth.users(id)" fails with
--     ERROR 42501: permission denied for schema auth. users.id is a plain uuid;
--     see section 3 for the optional CLI snippet to add the FK later.
--
-- RUNTIME auth.* CALLS KEPT (safe): auth.uid() / auth.jwt() inside policy
-- expressions and function BODIES are executed at query time under roles that
-- do have access (authenticated / service_role) — they never fail at DDL time
-- and are the standard Supabase RLS pattern. Only DDL *referencing* the auth
-- schema (FKs, triggers, CREATE IN auth) is blocked.
--
-- What this does:
--   1. Creates the app_role enum (super_admin | admin | agent)
--   2. Creates the workspaces table
--   3. Creates the users table (mirrors auth.users, holds display metadata)
--   4. Creates the workspace_members table (workspace-scoped roles)
--   5. Adds workspace_id to: customers, tickets, knowledge_base_chunks, calls
--   6. Builds indexes on all new workspace_id columns
--   7. Enables Row-Level Security on every tenant-owned table
--   8. Writes RLS policies (workspace isolation + super_admin bypass)
--   9. Replaces match_chunks() with a workspace-aware version
--  10. Creates public helper functions used inside RLS policies
--
-- Safe to run on a database with existing rows:
--   - workspace_id is added as NULLABLE first
--   - rows are backfilled to a "default" workspace created in this migration
--   - columns are then set NOT NULL
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 0. Extensions (idempotent — already present from earlier migrations)
-- ---------------------------------------------------------------------------
create extension if not exists "uuid-ossp";
create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------------------
-- 1. Enum: app_role
-- ---------------------------------------------------------------------------
do $$
begin
    if not exists (select 1 from pg_type where typname = 'app_role') then
        create type app_role as enum ('super_admin', 'admin', 'agent');
    end if;
end;
$$;

-- ---------------------------------------------------------------------------
-- 2. Table: workspaces
-- ---------------------------------------------------------------------------
create table if not exists workspaces (
    id          uuid primary key default uuid_generate_v4(),
    name        text not null,
    -- URL-safe unique identifier (e.g. "acme-telecom")
    slug        text not null,
    -- billing / feature tier: 'free' | 'pro' | 'enterprise'
    plan        text not null default 'free',
    is_active   boolean not null default true,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now(),

    constraint workspaces_slug_key unique (slug)
);

comment on table  workspaces       is 'Top-level tenant container. Every piece of customer data belongs to one workspace.';
comment on column workspaces.slug  is 'Unique, URL-safe identifier. Used in API paths and JWT claims.';
comment on column workspaces.plan  is 'Billing tier controlling feature access.';

-- Auto-bump updated_at on every UPDATE
create or replace function public.touch_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists workspaces_updated_at on workspaces;
create trigger workspaces_updated_at
    before update on workspaces
    for each row execute function public.touch_updated_at();

-- ---------------------------------------------------------------------------
-- 3. Table: users
-- ---------------------------------------------------------------------------
-- Mirrors auth.users (one row per Supabase Auth user). Holds display metadata
-- and the platform-level role (super_admin lives here, not in workspace_members).
-- Workspace-scoped roles (admin / agent) live in workspace_members below.
--
-- NOTE: NO foreign key to auth.users. Creating a constraint that references the
-- auth schema is blocked by Supabase SQL Editor permissions — this was the
-- source of "ERROR 42501: permission denied for schema auth". Referential
-- integrity is instead guaranteed by:
--   • public.handle_new_auth_user() inserting a matching row on every sign-up
--   • application code (auth middleware resolves user_id from the JWT)
--
-- OPTIONAL: to add the real FK later, run OUTSIDE the SQL Editor with a role
-- that owns/has rights on auth schema (supabase CLI db execute, or psql as
-- supabase_admin):
--   alter table users
--       add constraint users_id_fkey
--       foreign key (id) references auth.users (id) on delete cascade;
create table if not exists users (
    id            uuid primary key,
    email         text not null,
    display_name  text,
    -- Platform-level role. Only 'super_admin' is meaningful here;
    -- workspace roles are stored in workspace_members.
    platform_role app_role not null default 'agent',
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now()
);

comment on table  users               is 'Application-level user profile. id mirrors Supabase auth.users.id (no FK — see section 3 note).';
comment on column users.platform_role is 'super_admin bypasses all RLS. admin/agent use workspace_members.role instead.';

drop trigger if exists users_updated_at on users;
create trigger users_updated_at
    before update on users
    for each row execute function public.touch_updated_at();

-- ---------------------------------------------------------------------------
-- 4. Table: workspace_members
-- ---------------------------------------------------------------------------
-- Join table binding a user to a workspace with a workspace-scoped role.
-- A user can be a member of multiple workspaces with different roles.
create table if not exists workspace_members (
    id           uuid primary key default uuid_generate_v4(),
    workspace_id uuid not null references workspaces (id) on delete cascade,
    user_id      uuid not null references users (id) on delete cascade,
    -- Role within this specific workspace (admin | agent).
    -- super_admin does not need a workspace_members row — they bypass RLS globally.
    role         app_role not null default 'agent',
    invited_by   uuid references users (id) on delete set null,
    created_at   timestamptz not null default now(),
    updated_at   timestamptz not null default now(),

    -- A user has exactly one role per workspace
    constraint workspace_members_workspace_user_key unique (workspace_id, user_id)
);

comment on table workspace_members is 'Workspace-scoped role assignments. A user can hold different roles in different workspaces.';

create index if not exists idx_workspace_members_user_id
    on workspace_members (user_id);
create index if not exists idx_workspace_members_workspace_id
    on workspace_members (workspace_id);

drop trigger if exists workspace_members_updated_at on workspace_members;
create trigger workspace_members_updated_at
    before update on workspace_members
    for each row execute function public.touch_updated_at();

-- ---------------------------------------------------------------------------
-- 5. Thread workspace_id into existing tables
--
-- Step A: Add columns as nullable (so existing rows don't immediately violate NOT NULL)
-- Step B: Backfill using the "default" workspace created below
-- Step C: Set NOT NULL
-- ---------------------------------------------------------------------------

-- ---- Step A: Add nullable columns ----------------------------------------

alter table customers
    add column if not exists workspace_id uuid references workspaces (id) on delete restrict;

alter table tickets
    add column if not exists workspace_id uuid references workspaces (id) on delete restrict;

alter table knowledge_base_chunks
    add column if not exists workspace_id uuid references workspaces (id) on delete restrict;

-- The calls table is created by the application (not in a prior migration file).
-- This ALTER is safe whether the column already exists or not.
do $$
begin
    if exists (select 1 from information_schema.tables
               where table_schema = 'public' and table_name = 'calls') then
        if not exists (
            select 1 from information_schema.columns
            where  table_schema = 'public'
              and  table_name   = 'calls'
              and  column_name  = 'workspace_id'
        ) then
            alter table calls
                add column workspace_id uuid references workspaces (id) on delete restrict;
        end if;
    end if;
end;
$$;

-- ---- Step B: Create default workspace and backfill -----------------------

insert into workspaces (id, name, slug, plan)
values (
    'aaaaaaaa-0000-0000-0000-000000000001',
    'Default Workspace',
    'default',
    'free'
)
on conflict (slug) do nothing;

-- Backfill all existing rows that currently have a NULL workspace_id
update customers             set workspace_id = 'aaaaaaaa-0000-0000-0000-000000000001' where workspace_id is null;
update tickets               set workspace_id = 'aaaaaaaa-0000-0000-0000-000000000001' where workspace_id is null;
update knowledge_base_chunks set workspace_id = 'aaaaaaaa-0000-0000-0000-000000000001' where workspace_id is null;

do $$
begin
    if exists (select 1 from information_schema.tables
               where table_schema = 'public' and table_name = 'calls') then
        execute 'update calls set workspace_id = ''aaaaaaaa-0000-0000-0000-000000000001'' where workspace_id is null';
    end if;
end;
$$;

-- ---- Step C: Enforce NOT NULL --------------------------------------------

alter table customers             alter column workspace_id set not null;
alter table tickets               alter column workspace_id set not null;
alter table knowledge_base_chunks alter column workspace_id set not null;

do $$
begin
    if exists (select 1 from information_schema.tables
               where table_schema = 'public' and table_name = 'calls') then
        execute 'alter table calls alter column workspace_id set not null';
    end if;
end;
$$;

-- ---------------------------------------------------------------------------
-- 6. Indexes on workspace_id FK columns
-- ---------------------------------------------------------------------------

create index if not exists idx_customers_workspace_id
    on customers (workspace_id);

create index if not exists idx_tickets_workspace_id
    on tickets (workspace_id);

create index if not exists idx_knowledge_base_chunks_workspace_id
    on knowledge_base_chunks (workspace_id);

-- ---------------------------------------------------------------------------
-- 7. Enable Row-Level Security on every tenant-owned table
-- ---------------------------------------------------------------------------

alter table workspaces            enable row level security;
alter table users                 enable row level security;
alter table workspace_members     enable row level security;
alter table customers             enable row level security;
alter table tickets               enable row level security;
alter table knowledge_base_chunks enable row level security;

do $$
begin
    if exists (select 1 from information_schema.tables
               where table_schema = 'public' and table_name = 'calls') then
        execute 'alter table calls enable row level security';
    end if;
end;
$$;

-- ---------------------------------------------------------------------------
-- 8. RLS helper functions in PUBLIC schema
--
-- IMPORTANT: These are in public schema — NOT auth schema — because the
-- Supabase SQL Editor (postgres role) cannot create objects in the auth schema.
--
-- Both functions are SECURITY DEFINER so they read auth.jwt() / auth.uid()
-- with elevated privileges regardless of the calling context. The search_path
-- is locked to prevent privilege escalation.
-- ---------------------------------------------------------------------------

-- ---- helper: is the current JWT a super_admin? ---------------------------
-- Reads app_metadata.platform_role from the JWT payload.
-- app_metadata is set server-side only and cannot be forged by the client.
create or replace function public.is_super_admin()
returns boolean
language sql
stable
security definer
set search_path = public
as $$
    select coalesce(
        (auth.jwt() -> 'app_metadata' ->> 'platform_role') = 'super_admin',
        false
    );
$$;

-- ---- helper: set of workspace_ids the current user belongs to -----------
-- Returns every workspace_id from workspace_members for the calling auth.uid().
create or replace function public.my_workspace_ids()
returns setof uuid
language sql
stable
security definer
set search_path = public
as $$
    select workspace_id
    from   workspace_members
    where  user_id = auth.uid();
$$;

-- Grant execute to authenticated users only (anon has no identity to look up)
revoke execute on function public.is_super_admin()   from anon;
revoke execute on function public.my_workspace_ids() from anon;
grant  execute on function public.is_super_admin()   to authenticated, service_role;
grant  execute on function public.my_workspace_ids() to authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 9. Row-Level Security Policies
--
-- Design:
--   • All policies use public.is_super_admin() and public.my_workspace_ids()
--     (NOT auth.* — those are read-only from here).
--   • The service-role key bypasses RLS entirely (Postgres behaviour), so
--     backend code using the service key is unaffected by all policies below.
-- ---------------------------------------------------------------------------

-- =============================================================================
-- POLICIES: workspaces
-- =============================================================================
drop policy if exists "workspaces: super_admin full access" on workspaces;
create policy "workspaces: super_admin full access"
    on workspaces
    for all
    using  (public.is_super_admin())
    with check (public.is_super_admin());

drop policy if exists "workspaces: members can view their own workspace" on workspaces;
create policy "workspaces: members can view their own workspace"
    on workspaces
    for select
    using (id in (select public.my_workspace_ids()));

-- =============================================================================
-- POLICIES: users
-- =============================================================================
drop policy if exists "users: super_admin full access" on users;
create policy "users: super_admin full access"
    on users
    for all
    using  (public.is_super_admin())
    with check (public.is_super_admin());

-- Users can always view and edit their own profile
drop policy if exists "users: self view" on users;
create policy "users: self view"
    on users
    for select
    using (id = auth.uid());

drop policy if exists "users: self update" on users;
create policy "users: self update"
    on users
    for update
    using (id = auth.uid())
    with check (id = auth.uid());

-- Admins can view all users in their shared workspace(s)
drop policy if exists "users: admin views workspace members" on users;
create policy "users: admin views workspace members"
    on users
    for select
    using (
        id in (
            select wm.user_id
            from   workspace_members wm
            where  wm.workspace_id in (select public.my_workspace_ids())
              and  exists (
                  select 1
                  from   workspace_members me
                  where  me.user_id      = auth.uid()
                    and  me.workspace_id = wm.workspace_id
                    and  me.role in ('admin', 'super_admin')
              )
        )
    );

-- =============================================================================
-- POLICIES: workspace_members
-- =============================================================================
drop policy if exists "workspace_members: super_admin full access" on workspace_members;
create policy "workspace_members: super_admin full access"
    on workspace_members
    for all
    using  (public.is_super_admin())
    with check (public.is_super_admin());

drop policy if exists "workspace_members: members can view their workspace roster" on workspace_members;
create policy "workspace_members: members can view their workspace roster"
    on workspace_members
    for select
    using (workspace_id in (select public.my_workspace_ids()));

-- Only admins (and super_admin) can insert/update/delete membership records
drop policy if exists "workspace_members: admin manages membership" on workspace_members;
create policy "workspace_members: admin manages membership"
    on workspace_members
    for all
    using (
        workspace_id in (
            select wm.workspace_id
            from   workspace_members wm
            where  wm.user_id = auth.uid()
              and  wm.role    = 'admin'
        )
    )
    with check (
        workspace_id in (
            select wm.workspace_id
            from   workspace_members wm
            where  wm.user_id = auth.uid()
              and  wm.role    = 'admin'
        )
    );

-- =============================================================================
-- POLICIES: customers
-- =============================================================================
drop policy if exists "customers: super_admin full access" on customers;
create policy "customers: super_admin full access"
    on customers
    for all
    using  (public.is_super_admin())
    with check (public.is_super_admin());

drop policy if exists "customers: workspace isolation" on customers;
create policy "customers: workspace isolation"
    on customers
    for all
    using  (workspace_id in (select public.my_workspace_ids()))
    with check (workspace_id in (select public.my_workspace_ids()));

-- =============================================================================
-- POLICIES: tickets
-- =============================================================================
drop policy if exists "tickets: super_admin full access" on tickets;
create policy "tickets: super_admin full access"
    on tickets
    for all
    using  (public.is_super_admin())
    with check (public.is_super_admin());

drop policy if exists "tickets: workspace isolation" on tickets;
create policy "tickets: workspace isolation"
    on tickets
    for all
    using  (workspace_id in (select public.my_workspace_ids()))
    with check (workspace_id in (select public.my_workspace_ids()));

-- =============================================================================
-- POLICIES: knowledge_base_chunks
-- =============================================================================
drop policy if exists "knowledge_base_chunks: super_admin full access" on knowledge_base_chunks;
create policy "knowledge_base_chunks: super_admin full access"
    on knowledge_base_chunks
    for all
    using  (public.is_super_admin())
    with check (public.is_super_admin());

-- Any workspace member (agent or admin) can read KB chunks
drop policy if exists "knowledge_base_chunks: workspace read" on knowledge_base_chunks;
create policy "knowledge_base_chunks: workspace read"
    on knowledge_base_chunks
    for select
    using (workspace_id in (select public.my_workspace_ids()));

-- Only admins can write (insert / update / delete) KB chunks
drop policy if exists "knowledge_base_chunks: admin write" on knowledge_base_chunks;
create policy "knowledge_base_chunks: admin write"
    on knowledge_base_chunks
    for all
    using (
        workspace_id in (
            select wm.workspace_id
            from   workspace_members wm
            where  wm.user_id = auth.uid()
              and  wm.role    = 'admin'
        )
    )
    with check (
        workspace_id in (
            select wm.workspace_id
            from   workspace_members wm
            where  wm.user_id = auth.uid()
              and  wm.role    = 'admin'
        )
    );

-- =============================================================================
-- POLICIES: calls
-- =============================================================================
-- Applied via a DO block because the table might not exist in all environments.
do $$
begin
    if exists (select 1 from information_schema.tables
               where table_schema = 'public' and table_name = 'calls') then

        if not exists (
            select 1 from pg_policies
            where  tablename = 'calls'
              and  policyname = 'calls: super_admin full access'
        ) then
            execute $pol$
                create policy "calls: super_admin full access"
                    on calls for all
                    using  (public.is_super_admin())
                    with check (public.is_super_admin())
            $pol$;
        end if;

        if not exists (
            select 1 from pg_policies
            where  tablename = 'calls'
              and  policyname = 'calls: workspace isolation'
        ) then
            execute $pol$
                create policy "calls: workspace isolation"
                    on calls for all
                    using  (workspace_id in (select public.my_workspace_ids()))
                    with check (workspace_id in (select public.my_workspace_ids()))
            $pol$;
        end if;

    end if;
end;
$$;

-- ---------------------------------------------------------------------------
-- 10. workspace-aware match_chunks() — replaces the 768-dim version
--
-- Added parameter: filter_workspace_id uuid
-- The workspace filter is applied alongside the existing category filter so
-- hybrid search NEVER returns another workspace's documents, even if there
-- is a bug in the application layer.
-- ---------------------------------------------------------------------------
create or replace function public.match_chunks(
    query_embedding     vector(768),
    query_text          text,
    filter_category     text,
    filter_workspace_id uuid,                -- NEW: mandatory workspace scope
    match_count_dense   int  default 20,
    match_count_sparse  int  default 20,
    rrf_k               int  default 60,
    match_count         int  default 5
)
returns table (
    id       uuid,
    content  text,
    metadata jsonb,
    score    double precision
)
language sql
stable
set search_path = public
as $$
    with dense as (
        select
            id, content, metadata,
            row_number() over (order by embedding <=> query_embedding) as rnk
        from  knowledge_base_chunks
        where metadata->>'category' = filter_category
          and workspace_id          = filter_workspace_id      -- workspace guard
        order by embedding <=> query_embedding
        limit match_count_dense
    ),
    sparse as (
        select
            id, content, metadata,
            row_number() over (
                order by ts_rank(fts_tokens, websearch_to_tsquery('simple', query_text)) desc
            ) as rnk
        from  knowledge_base_chunks
        where metadata->>'category' = filter_category
          and workspace_id          = filter_workspace_id      -- workspace guard
          and fts_tokens @@ websearch_to_tsquery('simple', query_text)
        order by ts_rank(fts_tokens, websearch_to_tsquery('simple', query_text)) desc
        limit match_count_sparse
    ),
    fused as (
        select
            id,
            max(content)  as content,
            max(metadata) as metadata,
            sum(1.0 / (rrf_k + rnk)) as score
        from (
            select * from dense
            union all
            select * from sparse
        ) combined
        group by id
    )
    select id, content, metadata, score
    from   fused
    order  by score desc
    limit  match_count;
$$;

-- Grant execute to authenticated and service_role (anon must not call this directly)
revoke execute on function public.match_chunks(vector, text, text, uuid, int, int, int, int) from anon;
grant  execute on function public.match_chunks(vector, text, text, uuid, int, int, int, int) to authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 11. Auto-profile function (trigger body only — trigger registered separately)
--
-- The trigger that fires this on auth.users INSERT cannot be created from the
-- SQL Editor (the auth schema is read-only from here). Two options:
--
--   OPTION A (Recommended — zero code): Supabase Dashboard
--     1. Go to Database → Triggers → "New trigger"
--     2. Table: auth.users  |  Events: INSERT  |  Timing: AFTER
--     3. Function: public.handle_new_auth_user
--     4. Save.
--
--   OPTION B (CLI / psql as supabase_admin):
--     Run the two statements below via:
--       supabase db execute --sql "drop trigger if exists on_auth_user_created on auth.users;"
--       supabase db execute --sql "create trigger on_auth_user_created after insert on auth.users for each row execute function public.handle_new_auth_user();"
--
-- Until the trigger is created, manually insert a row into public.users after
-- creating your first Supabase Auth account (see 001_seed_workspace.sql).
-- ---------------------------------------------------------------------------
create or replace function public.handle_new_auth_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
    insert into public.users (id, email, display_name, platform_role)
    values (
        new.id,
        new.email,
        coalesce(new.raw_user_meta_data->>'display_name', split_part(new.email, '@', 1)),
        'agent'::app_role   -- all new sign-ups are agents; promote via seed/admin API
    )
    on conflict (id) do nothing;
    return new;
end;
$$;

-- Trigger registration SQL for reference — run via Dashboard or CLI (see above):
-- drop trigger if exists on_auth_user_created on auth.users;
-- create trigger on_auth_user_created
--     after insert on auth.users
--     for each row execute function public.handle_new_auth_user();

-- =============================================================================
-- Migration complete.
-- =============================================================================
-- Next step: register the auth trigger via Supabase Dashboard → Database →
-- Triggers, OR via the Supabase CLI. See section 11 above.
-- =============================================================================
