-- =============================================================================
-- Migration 007: fix RLS infinite recursion on workspace_members / users
--
-- BUG (verified live): any anon/authenticated query on workspace_members or
-- users failed with:
--   42517 infinite recursion detected in policy "workspace_members"
-- because the "admin manages membership" policy SELECTed from
-- workspace_members INSIDE its own USING clause.
--
-- FIX: the self-referencing lookup moves into a SECURITY DEFINER helper
-- (runs as owner, bypasses RLS on itself) and the policy just calls it.
-- =============================================================================

-- helper: workspaces where the caller is an ADMIN
create or replace function public.my_admin_workspace_ids()
returns setof uuid
language sql
stable
security definer
set search_path = public
as $$
    select workspace_id
    from workspace_members
    where user_id = auth.uid()
      and role = 'admin'
$$;

revoke execute on function public.my_admin_workspace_ids() from anon;
grant  execute on function public.my_admin_workspace_ids()
       to authenticated, service_role;

-- ---------------------------------------------------------------------------
-- rewrite the recursive policy
-- ---------------------------------------------------------------------------
drop policy if exists "workspace_members: admin manages membership"
    on workspace_members;
create policy "workspace_members: admin manages membership"
    on workspace_members
    for all
    using (workspace_id in (select public.my_admin_workspace_ids()))
    with check (workspace_id in (select public.my_admin_workspace_ids()));

-- ---------------------------------------------------------------------------
-- "users: admin views workspace members" also chained into workspace_members
-- RLS — rewrite it with the helper (same semantics, no recursion)
-- ---------------------------------------------------------------------------
drop policy if exists "users: admin views workspace members" on users;
create policy "users: admin views workspace members"
    on users
    for select
    using (
        id in (
            select wm2.user_id
            from workspace_members wm2
            where wm2.workspace_id in (select public.my_admin_workspace_ids())
        )
    );
