-- =============================================================================
-- Migration 004: Agent-level ticket assignment (data visibility)
-- Run in Supabase SQL Editor. Idempotent.
--
-- Why: the visibility model is
--   agent       -> sees only tickets/calls ASSIGNED to them
--   admin       -> sees all data inside their workspace
--   super_admin -> sees everything, any workspace
-- Tickets previously had no "assigned to which CSR" column, so agent-level
-- scoping was impossible. This adds it.
--
-- NOTE: no FK to auth.users — same SQL Editor restriction as 003 (42501).
-- =============================================================================

alter table tickets
    add column if not exists assigned_to uuid;

comment on column tickets.assigned_to is
    'CSR (public.users.id) responsible for this ticket. NULL = unassigned; admins/super_admins see it, agents do not.';

create index if not exists idx_tickets_assigned_to on tickets (assigned_to);

-- Backfill: leave existing rows unassigned (visible to admins only) —
-- do NOT guess an owner for historical data.
