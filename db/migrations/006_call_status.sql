-- =============================================================================
-- Migration 006: call connection status (answered / busy / no-answer ...)
-- Run in Supabase SQL Editor. Idempotent.
-- =============================================================================

alter table calls add column if not exists call_status text;

comment on column calls.call_status is
    'Connection result from Vonage events: dialing | ringing | answered | busy | rejected | cancelled | failed | timeout | completed.';
