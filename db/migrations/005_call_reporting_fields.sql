-- =============================================================================
-- Migration 005: call reporting fields (duration / timestamps / ticket ref)
-- Run in Supabase SQL Editor. Idempotent.
--
-- Why: calls previously had nowhere to record when the call started, how long
-- it lasted, or a human-readable ticket reference ("T-1001" can't go in the
-- uuid ticket_id column) — so reports were thin and inserts silently dropped.
-- =============================================================================

alter table calls add column if not exists started_at       timestamptz;
alter table calls add column if not exists ended_at         timestamptz;
alter table calls add column if not exists duration_seconds integer;
alter table calls add column if not exists ticket_ref       text;

comment on column calls.ticket_ref is 'Human-readable ticket label (e.g. T-1001); uuid FK stays in ticket_id.';
