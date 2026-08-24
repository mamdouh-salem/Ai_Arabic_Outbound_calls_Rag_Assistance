-- =============================================================================
-- Seed 001: Default Workspace for Development
--
-- Creates the canonical "default" workspace used by the migration backfill,
-- and (optionally) creates a super_admin user record so you can immediately
-- test RLS bypass without going through the sign-up flow.
--
-- Run AFTER 003_multi_tenancy.sql.
-- This file is idempotent — safe to run multiple times.
-- =============================================================================

-- Default workspace (matches the UUID used in the migration backfill)
insert into workspaces (id, name, slug, plan, is_active)
values (
    'aaaaaaaa-0000-0000-0000-000000000001',
    'Default Workspace',
    'default',
    'free',
    true
)
on conflict (slug) do update
    set name      = excluded.name,
        is_active = excluded.is_active;

-- ---------------------------------------------------------------------------
-- Optional: promote a specific Supabase Auth user to super_admin.
--
-- Uncomment and replace the UUID below with the user's auth.users.id after
-- you create your first account via the Supabase Auth dashboard or sign-up flow.
-- ---------------------------------------------------------------------------
-- update users
--    set platform_role = 'super_admin'
--  where id = '<your-supabase-auth-user-uuid>';

-- ---------------------------------------------------------------------------
-- Optional: add that super_admin as an admin of the default workspace
-- so they can also manage workspace data without needing app_metadata bypass.
-- ---------------------------------------------------------------------------
-- insert into workspace_members (workspace_id, user_id, role)
-- values (
--     'aaaaaaaa-0000-0000-0000-000000000001',
--     '<your-supabase-auth-user-uuid>',
--     'admin'
-- )
-- on conflict (workspace_id, user_id) do update set role = 'admin';
