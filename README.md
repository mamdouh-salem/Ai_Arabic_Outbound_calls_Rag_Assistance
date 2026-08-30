# Multi-Agent Arabic Outbound Calls + RAG Knowledge Assistant

Arabic (Egyptian) AI voice agent that calls back customers with open tickets, verifies whether the
procedure from their previous inbound call actually resolved the issue, tries to help from the
internal knowledge base if it did not, and hands the live call over to a human customer-service
representative — who then gets a RAG co-pilot beside them.

Built from the two use cases in `docs/00_use_case.md`:
- **UC1** — AI-powered outbound follow-up calls (Arabic STT/TTS, branching dialog, FCR report).
- **UC2** — Arabic chatbot over the internal knowledge base (RAG assistant for the human agent).

> **v2 scope note:** the project is moving from an internal single-tenant ops tool to a
> multi-tenant product with real sign-up, a proper web frontend, workspace-level access control,
> and document-upload RAG. See [Phase 2 Requirements](#phase-2-requirements) below — this is the
> active work as of this update.

## End-to-end flow

```
                    ┌──────────────────────────────────────────────────┐
                    │  Supabase: customers + tickets (open/unresolved)  │
                    └───────────────────────┬──────────────────────────┘
                                            │ campaign picks due tickets
                                            ▼
                                   ┌────────────────────┐
                                   │  Outbound Call     │  auto-dials (simulated → Vonage later)
                                   │  Agent  (Arabic)   │  TTS greeting + ticket context
                                   └─────────┬──────────┘
                                             │  customer speaks → STT (Whisper, ar)
                                             ▼
                                   ┌────────────────────┐
                                   │ Intent Classifier  │ resolved | unresolved | unclear | wants_human
                                   └───┬────────────┬───┘
                        "نعم" resolved │            │ "لا" / "غير متأكد"
                                       ▼            ▼
                              ┌─────────────┐   ┌────────────────────┐
                              │  Reporting  │   │  KB Assist Agent   │ hybrid search + metadata
                              │   Agent     │   │  (in-call RAG)     │ filter + rerank + grounding
                              └──────┬──────┘   └─────────┬──────────┘
                                     │                    │ still unresolved / asks for human
                                     │                    ▼
                                     │          ┌────────────────────┐
                                     │          │  Routing Agent     │ priority + escalation +
                                     │          │                    │ RAG brief for the human
                                     │          └─────────┬──────────┘
                                     │                    │ graph interrupt → state checkpointed
                                     │                    ▼
                                     │          ┌────────────────────┐
                                     │          │  Human CSR (Agent  │ takes over the live call,
                                     │          │  Desk) + RAG chat  │ RAG co-pilot answers in Arabic
                                     │          │  co-pilot          │ with cited KB sources
                                     │          └─────────┬──────────┘
                                     ▼                    ▼
                              ┌───────────────────────────────────────┐
                              │ Call log, outcome, duration, transcript │
                              │      → "First Call Resolutions" report  │
                              └───────────────────────────────────────┘
```

## Stack

| Layer | Choice |
|---|---|
| Agent harness / prompting | LangChain (LCEL, structured output) |
| Agentic workflow | LangGraph (`StateGraph`, conditional edges, dependency-injected voice/RAG/intent ports, `interrupt` for human handoff) |
| Tracing & visualization | LangSmith |
| Generation LLM | Pluggable via `GENERATION_PROVIDER`: local Qwen2.5-7B-Instruct (4-bit) / OpenAI (`gpt-4o-mini`) / Gemini (`gemini-3.6-flash`) — same call site (`common/local_llm.py`), swap by env var only |
| Embeddings | Local: `sentence-transformers/paraphrase-multilingual-mpnet-base-v2` (768-dim) |
| STT | OpenAI Whisper family, Arabic — **moving to an Egyptian-dialect fine-tune, see below** |
| TTS | ElevenLabs multilingual — **voice selection being tightened for Egyptian dialect, see below** |
| Database + vectors | Supabase Postgres + pgvector (one store: business data **and** KB chunks) |
| Retrieval | Hybrid = dense (pgvector, `vector(768)`) + sparse (Postgres full-text) fused with RRF, metadata (`jsonb`) category filtering |
| Backend | FastAPI |
| UI | Gradio (internal ops console) → **being replaced by a real web frontend, see below** |
| Auth | **New** — Supabase Auth (email/password + magic link), JWT-based sessions, workspace-scoped roles |
| Telephony | Simulated adapter now; **Vonage** adapter next (voice/telephony ports already isolated for this swap) |

## Layout

```
docs/                       design docs (architecture, data model, agent contracts, RAG design)
data/knowledge_base/        handcrafted Arabic KB source documents
data/seeds/                 seed customers / tickets
data/eval/                  ground-truth Q→answer→source pairs for RAG evaluation
db/migrations/              SQL: extensions, core tables, KB tables, indexes, hybrid search fn
db/seed/                    seed SQL
scripts/                    ingest_kb, embed_kb_chunks, seed_db, eval_rag, test_settings,
                             smoke_test_graph, smoke_test_graph_real, run_api, run_ui
src/outbound_ai/
  common/                   shared pure helpers (Arabic normalization, local_llm provider switch)
  config/                   settings (pydantic-settings), logging, LangSmith tracing setup
  schemas/                  pydantic models shared across API, graph and UI
  db/                       Supabase client + repositories (the only layer that touches the DB)
  auth/                     [new] sign-up/login, JWT session handling, role + workspace checks
  prompts/                  the LangChain harness — one module per agent, versioned separately
  agents/                   intent_classifier, kb_assist done; outbound_call, routing, reporting pending
  rag/                      loaders, chunking, embeddings, filters, retrievers/, rerank,
                            grounding, pipeline, generation, [new] ingestion API + citation formatting
  voice/                    STT/TTS ports + Whisper and ElevenLabs adapters, VAD, audio utils
  telephony/                telephony port + simulated adapter (+ Vonage adapter pending)
  orchestration/            [new] call queue/worker layer — campaign scheduling, concurrency
                             limits, retries, webhook idempotency (sits above the LangGraph)
  graph/                    LangGraph state, nodes, edges, deps (DI), compiled graph
  api/                      FastAPI app and routers (not started)
  ui/                       Gradio app — kept only as an internal debug console going forward;
                             the product frontend moves to web/ (see below)
web/                        [new] real frontend (React/Next.js) — campaign, live call, agent
                            desk, KB admin (with document upload), reports, auth screens
tests/                      unit / integration / fixtures
```

**Design rules:** `voice/` and `telephony/` are ports with adapters, so swapping the simulator for
Vonage touches no graph code. `prompts/` is separate from `agents/` so prompt engineering is
versioned and A/B-testable without editing logic. `db/repositories/` is the only place Supabase is
imported, so schema changes stay local. `common/local_llm.py` hides which generation provider
(local/OpenAI/Gemini) is active behind one `run_chat()` call, so `rag/generation.py` and
`agents/intent_classifier.py` never need to know or change when the provider switches.

## Setup

Python 3.11 (3.13+ not yet supported by parts of the stack).

```bash
uv venv --python 3.11
uv pip install -e ".[dev]"
cp .env.example .env
```

### Shared Supabase project (all team members)

The team works against ONE shared Supabase project. The connection keys are
**pre-filled in `.env.example`** — after `cp .env.example .env` you're already
connected; nothing else to configure.

> ⚠️ **Handle with care:**
> - `SUPABASE_ANON_KEY` — safe: every write goes through RLS policies
> - `SUPABASE_SERVICE_ROLE_KEY` — **bypasses ALL RLS**; never use it in
>   frontend code, and never commit it anywhere else
> - `DATABASE_URL` — direct Postgres with full access; same caution
> - The repo must stay **private** while these are committed

To apply the database schema on a fresh project, run the migrations in order
in the SQL Editor:

```
db/migrations/001_base_schema.sql   → 003_multi_tenancy.sql
→ 004_ticket_assignment.sql         → 005_call_reporting_fields.sql
→ 006_call_status.sql               → db/seed/001_seed_workspace.sql
```

(002 is historical — its index and function are superseded by 001 and 003.)

Run the tests (no API keys needed — the voice layer has fakes):

```bash
pytest tests/unit -q
```

Sanity-check config and the graph before touching anything else:

```bash
python scripts/test_settings.py          # settings.py loads .env correctly, tracing env vars export
python scripts/smoke_test_graph.py       # graph runs end-to-end against fake voice/KB/intent adapters
python scripts/smoke_test_graph_real.py  # same graph, real intent classification + real RAG retrieval/generation
```

---

## Auth & multi-tenancy setup (Phase 2)

Implemented so far: `users` / `workspaces` / `workspace_members` tables with RLS,
JWT verification middleware (`auth/middleware.py`), role guards
(`auth/dependencies.py`: `get_current_user`, `require_admin_or_above`,
`require_super_admin`), `/health/auth` probe endpoint, 26 unit tests.

### One-time database setup (Supabase SQL Editor)

1. Run `db/migrations/003_multi_tenancy.sql`
   - Adds `workspace_id` to `customers`/`tickets`/`knowledge_base_chunks`/`calls`,
     backfills everything into the `default` workspace, enables RLS, replaces
     `match_chunks()` with a workspace-aware version.
   - Note: no FK to `auth.users` — the SQL Editor role cannot create DDL
     referencing the auth schema (ERROR 42501). Integrity is handled by the
     profile hook + JWT middleware instead.
2. Run `db/seed/001_seed_workspace.sql` (idempotent).

### Environment

```bash
# .env — find the value in Dashboard → Project Settings → API → JWT Secret
SUPABASE_JWT_SECRET=<your-jwt-secret>
```

### First super_admin bootstrap

There is no sign-up endpoint yet (next phase of work), so create the first
account manually:

1. Dashboard → Authentication → Users → **Add user** (email + password).
2. Copy the user's UUID, then in the SQL Editor:

   ```sql
   insert into users (id, email, display_name, platform_role)
   values ('<auth-user-uuid>', '<email>', '<name>', 'super_admin')
   on conflict (id) do update set platform_role = 'super_admin';
   ```

3. Optional — also make them admin of the default workspace (needed for
   workspace-scoped writes even as super_admin when using the anon key):

   ```sql
   insert into workspace_members (workspace_id, user_id, role)
   values ('aaaaaaaa-0000-0000-0000-000000000001', '<auth-user-uuid>', 'admin')
   on conflict (workspace_id, user_id) do update set role = 'admin';
   ```

### Auto-profile trigger (optional, recommended)

New sign-ups won't get a `public.users` row automatically until this trigger
exists (cannot be created from the SQL Editor):

Dashboard → Database → Triggers → New trigger → table `auth.users`,
event `INSERT`, timing AFTER, function `public.handle_new_auth_user`.
Or via CLI:

```bash
supabase db execute --sql "create trigger on_auth_user_created after insert on auth.users for each row execute function public.handle_new_auth_user();"
```

### Verifying auth works

```bash
uvicorn outbound_ai.api.app:app --reload   # or scripts/run_api if present
curl http://localhost:8000/health                       # unauthenticated → {"status":"ok"}
curl http://localhost:8000/health/auth -H "Authorization: Bearer <jwt>"   # → identity JSON
```

---

## Phase 2 requirements

Feedback from review: the demo proved the concept works, but four gaps block it from being a
real product. This section captures what's changing and who owns it.

### 1. Sign-up / authentication

Currently there is no end-user identity at all — the Gradio console is a shared internal tool.
Phase 2 adds real accounts:

- **Supabase Auth** (already using Supabase for data, so no new vendor) handles sign-up, login,
  password reset, and session tokens (JWT).
- Every API request carries a JWT; FastAPI middleware resolves it to `(user_id, workspace_id, role)`.
- This is required *before* multi-tenancy (#4 below) can work, since every table needs to know
  which user/workspace a row belongs to.

### 2. Real frontend (replacing Gradio)

Gradio was fine for internal smoke-testing but isn't a product UI (no auth screens, weak
componentization, hard to theme, not built for role-based views). Plan:

- **React + Next.js**, talking to the existing FastAPI backend over REST (the API layer barely
  exists yet, so frontend and backend work should be designed together, not sequentially).
- Screens: sign-up/login, campaign trigger, live call monitor, agent desk (RAG co-pilot chat),
  KB admin (upload + browse documents), reports/FCR dashboard, workspace/user management (for
  admins).
- Gradio doesn't disappear — it stays as an internal debug console in `ui/` for engineers testing
  the graph directly, separate from the product frontend in `web/`.

### 3. RAG: document upload + citations

Today the KB is hand-authored SOP files ingested once via a script — there's no way for an admin
to upload a new policy doc, and answers don't tell the CSR (or the customer-facing agent) *where*
an answer came from. Two additions to `rag/`:

- **Ingestion API**: an authenticated endpoint (`POST /kb/documents`) that accepts PDF/DOCX/TXT,
  runs the existing chunking → embedding → `knowledge_base_chunks` pipeline, and tags chunks with
  `workspace_id` + category metadata. This reuses the current chunking/embedding code — it just
  needs an HTTP entry point instead of a one-off script.
- **Citations**: `rag/generation.py` already retrieves chunks with source metadata; it just needs
  to (a) pass chunk IDs/source doc names through to the generated answer, and (b) have the
  frontend render them as clickable source references next to the answer. This is mostly plumbing
  — the retrieval side already has what's needed.

### 4. Multi-tenancy: super admin / admin / user roles

Three-tier model, each workspace-scoped except the top tier:

| Role | Scope | Can do |
|---|---|---|
| **Super admin** | Platform-wide | Create/suspend workspaces, manage billing, assign workspace admins, manage users across ALL workspaces. **Cannot make outbound calls.** |
| **Admin** | One workspace | Manage users within their workspace, upload/edit/delete KB documents, configure campaigns, view all reports/call logs, **make outbound calls**, use RAG chat/voice, run SQL queries. |
| **User (CSR/agent)** | One workspace | Take over escalated calls, use the RAG co-pilot (chat/voice) at the agent desk, view tickets assigned to them. **Cannot** upload/delete KB docs, manage users, or make calls. |

Implementation approach:
- Add a `workspaces` table; add `workspace_id` FK to `customers`, `tickets`,
  `knowledge_base_chunks`, and a new `users`/`workspace_members` table with a `role` column.
- Enforce isolation with **Postgres Row-Level Security (RLS) policies** in Supabase, keyed on
  `workspace_id` from the JWT claims — not just application-layer checks. This means even a bug
  in the FastAPI layer can't leak one workspace's data into another's queries.
- RAG retrieval (`match_chunks`) needs a `workspace_id` filter added alongside the existing
  category filter, so hybrid search never returns another workspace's documents.

---

## Voice AI: fixing transcription accuracy and dialect

Two separate problems were flagged, and they need two separate fixes because they sit in
different parts of the pipeline:

**A. Whisper mis-transcribing (listening/STT):** the base Whisper models are trained mostly on
Modern Standard Arabic and general multilingual data, so they under-perform on Egyptian
colloquial speech — that's a training-data mismatch, not a bug. Fine-tuned Egyptian-dialect
Whisper checkpoints exist and are drop-in replacements (same architecture, just different
weights), for example `whisper-medium-egy` and LoRA-tuned `whisper-large-v3` variants trained on
Egyptian ASR datasets (MGB-3-style corpora). Recommendation: benchmark 2–3 of these against your
own call recordings and swap the model ID in the Whisper adapter — no pipeline changes needed
since `voice/` already treats STT as a port.

**B. Output not in Egyptian dialect (thinking/generation):** this is a prompting problem, not a
model problem — the LLM (Qwen/Gemini/GPT) defaults to MSA unless explicitly told otherwise.
Fix: tighten the system prompts in `prompts/` to explicitly instruct Egyptian colloquial Arabic
(with a few in-context examples of the target register), and consider adding a
"dialect-consistency" check as a lightweight validation step before TTS. This is pure prompt
engineering — cheap to iterate on since `prompts/` is already versioned separately from `agents/`.

**C. TTS not sounding Egyptian (speaking):** ElevenLabs' multilingual model treats "Arabic" as one
undifferentiated language rather than per-dialect — it has several voices *labeled* Egyptian
(e.g. Haytham, Amr, Marco Nady) but overall Arabic dialect depth is a known weak point of the
platform relative to Arabic-first TTS vendors. Two paths: (1) explicitly pin the adapter to one of
ElevenLabs' Egyptian-tagged voices and validate it sounds right, which is the fastest fix and
needs no vendor change; or (2) if quality still isn't good enough, evaluate an Arabic-dialect-first
TTS provider as a second adapter behind the existing `TTSPort` — the port/adapter design means
this doesn't touch `graph/` or `agents/` either way.

---

## Do you need a call-orchestration layer?

**Short answer: yes, and you likely need two layers, not one, because they solve different problems.**

- **Conversation orchestration** (already built): LangGraph's `StateGraph` handles *what happens
  during one call* — routing between intent classifier, KB assist, escalation, reporting. This
  part is done and doesn't change.
- **Call orchestration** (not built yet, needed for Vonage): handles *the calls themselves* —
  which tickets are due to be called, how many calls run concurrently, retrying no-answers,
  making sure a Vonage webhook that fires twice doesn't process the same call twice, and
  persisting call state so a server restart doesn't lose an in-progress call. None of this lives
  naturally inside a LangGraph node.

Recommended shape: a small `orchestration/` layer (a queue — Celery+Redis or even a simple
Postgres-backed job table — sitting between "campaign picks due tickets" and "dial via Vonage
adapter"). It calls into the existing graph per call; it doesn't replace it. This is also exactly
where the **PostgreSQL-backed LangGraph checkpointer** (already on the backlog) becomes required —
in-process `MemorySaver` can't survive the kind of restarts/retries a real call queue needs to
handle gracefully.

---

## Suggested team split (4 people)

You've asked to own the **agentic voice AI** (graph, voice ports, Vonage integration, call
orchestration) and the **RAG system** (retrieval, ingestion, citations). Rough split for the
other three, grouped so each person can work with minimal cross-blocking:

| Owner | Area | Covers |
|---|---|---|
| **Teammate A** | Agentic voice AI + RAG | LangGraph agents (`outbound_call`, `routing`, `reporting`), Vonage telephony adapter, `orchestration/` call queue, PostgreSQL checkpointer, dialect fixes (STT/TTS/prompting), RAG ingestion API + citations, hybrid retrieval workspace-scoping |
| **Teammate B** | Frontend | `web/` React+Next.js app: auth screens, campaign UI, live call monitor, agent desk chat UI, KB admin (upload UI), reports dashboard |
| **Teammate C** | Backend + Auth + Multi-tenancy | FastAPI routers (`api/`), Supabase Auth integration, `workspaces`/`users` schema + RLS policies, role/permission middleware |
| **Teammate D** | Data/DB + QA + Reporting | DB migrations for the new tables, seed data for multi-tenant testing, `eval_rag` expansion, FCR reporting logic, integration test coverage across the whole flow |

Interfaces to agree on early so nobody blocks anyone: the JWT claims shape (Teammate C defines,
everyone else consumes), the KB upload API contract (Teammate A + Teammate B), and the workspace_id
threading through every table (Teammate C + Teammate D).

---

## Status (updated — Phase 2 backend & voice agent COMPLETE)

Everything below is merged into the working tree and verified against a live
Supabase + live Vonage trial line. **75 unit tests green.**

**Done — original phase 1:**
- Project scaffolding, configuration, Arabic normalization
- Voice layer ports (`STTPort` / `TTSPort` / `EndpointingPort`) + Whisper, ElevenLabs, and
  push-to-talk adapters, streaming sentence chunker, fakes for testing
- Database schema — `customers`, `tickets`, `knowledge_base_chunks`
  (`vector(768)` embeddings, category metadata, FTS tokens), seeded data
- RAG pipeline — hybrid search (dense pgvector + sparse full-text fused with RRF),
  metadata filtering, grounded generation; pluggable provider (local Qwen / OpenAI / Gemini)
- LangGraph workflow — state/edges/nodes/build with dependency injection,
  conditional routing, diagram in `graph_workflow.png` (also served at `/workflow.png`)
- `agents/intent_classifier.py`, `agents/kb_assist.py` — proven against real LLM + real retrieval

**Done — phase 2 (this branch):**
- **Multi-tenancy DB** — migrations 003–006: `workspaces`, `users`,
  `workspace_members` with RLS policies, `workspace_id` threaded through every
  tenant table + backfilled; SQL-Editor-safe (no auth-schema DDL)
- **Auth foundation** — Supabase JWT verification middleware supporting BOTH
  legacy HS256 secret and current ES256 asymmetric keys via JWKS; role guards
  (`get_current_user`, `require_admin_or_above`, `require_super_admin`);
  open self sign-up endpoint; auto-profile hook function
- **User management** — super admin creates admin/agent accounts (Supabase Auth
  admin API, one-time generated passwords); platform-role changes; hierarchical
  user listing; platform hierarchy tree (workspace → admins → agents)
- **Workspace management** — create/list workspaces; add members; super-admin
  workspace scoping bar across all data endpoints (`X-Workspace-Id`)
- **KB management API + console UI** — upload `.txt/.md/.pdf/.docx/.csv/.json`
  (or pasted Arabic text) → chunk → embed → store, workspace-scoped; list/delete
- **RAG chat assistant with citations** — `/kb/chat`: grounded Arabic answers +
  per-chunk citations (index/source/score/snippet), role-scoped retrieval
- **Live outbound calling (Vonage)** — one-click "Call" from the Tickets tab;
  greeting with time-of-day + customer name + ticket title; guided multi-stage
  conversation: resolution check → clarification request → KB similarity search
  → Egyptian-dialect troubleshooting step ("لما تخلص قولّي خلصت") → completion
  confirmation → final verdict → thanks or human transfer; negation-aware
  resolution detection ("متحلتش" ≠ "اتحلت"); honest KB dead-end handoff
- **Voice** — ElevenLabs audio streamed into live calls (single consistent
  voice; Vonage TTS only as emergency fallback); looping hold message that
  never outlives processing
- **Reliability fixes** — mid-call NCCO transfer changes the conversation uuid:
  new conversations are now adopted so stage-2 answers always arrive; startup
  warm-up pre-loads the embedding model + hold audio; whole stage pipeline is
  failure-proofed (apology + transfer + report row on any error)
- **Reporting** — call reports with connection status (answered/busy/no-answer/
  rejected/failed), start/end timestamps, duration, transcript, KB answer,
  sources; outcome resolved ONLY when the customer confirms it; detailed Calls
  table view
- **Browser console SPA** — served by FastAPI at `/`: login/sign-up screens,
  role-aware navigation (agent/admin/super admin), dashboard with workflow
  diagram, tickets/calls tables, KB manager, user & workspace management,
  call center, RAG chat

**Done — latest RAG developments (manager requests):**
- **Voice in the RAG chat** — `POST /kb/chat/voice`: record a question in the
  console (mic button) → Gemini STT → grounded answer → ElevenLabs spoken
  reply played back; shared `voice_services` module reused by the live-call flow
- **Customizable personas** — six response styles selectable per request
  (default / Egyptian friendly / formal / concise / empathetic / technical)
- **Answer languages** — any persona × any language: Arabic (native),
  English, Spanish, German, French; spoken replies follow the chosen language
- **Structured data (NL → SQL)** — `POST /data/query` + "Data Insights" tab:
  ask business-data questions in plain language; the LLM writes a SELECT over
  the known schema, hard-validated (SELECT-only, single statement, forbidden
  keywords, forced LIMIT) and executed read-only with a statement timeout
- **Base schema versioned** — `001_base_schema.sql` reconstructed from the
  live database (all four core tables, indexes, Arabic FTS trigger), verified
  idempotent against production
- **Workflow visualization** — `/workflow.png` served from the compiled graph
  and embedded in the Dashboard; local LangGraph Studio wiring included
  (`langgraph.json` + `graph/studio.py`, runs via `langgraph dev` — no deployment)

## Upcoming steps — by owner

> **Teammate A (voice AI + RAG): COMPLETE.** Everything in the backend/agents/
> RAG/voice scope is implemented, tested (97 unit tests) and verified live.
> Remaining backend items below are optional polish, pick them up if/when
> capacity allows.

| Owner | Area | Next tasks |
|---|---|---|
| **Teammate B** | Frontend | **Implement your styling** on the console SPA (`api/static/`): your own design system/theme over the existing screens, RTL polish for Arabic views, responsive layout, loading/empty states, then the React/Next.js migration (`web/`) when the design is approved. REST contracts stay as-is. |
| **Teammate C** | Database | **Own the schema**: steward the migrations folder (001–006) as the single source of truth, write the seed-data set for multi-tenant testing, RLS policy audit (try to break isolation between two workspaces), add performance indexes for the reporting queries, document a backup/restore runbook. |
| **Teammate D** | Quality | **Quality gate**: run + extend the 97-test suite, add integration tests for the call stage machine (mock Vonage events: answered/busy/no-answer/abandoned), regression tests for the negation/resolution logic, expand `data/eval` and re-run `eval_rag`, verify the NL→SQL guards (try injection patterns), sign off releases. |
| **Team Lead** | Integration | Review + merge this branch into `main`; register the auto-profile trigger (Dashboard → Triggers); production Vonage number + account upgrade; rotate the shared Supabase keys if the repo ever goes public. |

Known temporary workarounds (dev-only): customers share one phone number
(trial Vonage restriction) with the unique constraint dropped — restore
`customers_phone_key` before production; `docs_url` enabled while `APP_ENV=dev`.

### Workflow diagram & interactive LangGraph Studio (local — no deployment)

- **Diagram:** served at `/workflow.png` and embedded in the console Dashboard;
  generated straight from the compiled graph — no LangSmith login required.
- **Interactive Studio:** step through nodes, inspect/edit state, replay runs —
  runs entirely on your machine via the dev server (`langgraph.json` registers
  `outbound_agent` → `src/outbound_ai/graph/studio.py`, which wires REAL Gemini
  intent classification and REAL Supabase RAG; only audio ports are silent).

  ```bash
  # one-time — keep it in a SEPARATE venv: langgraph-cli pulls a newer
  # langchain-core than the pinned API dependencies in .venv tolerate.
  rm -rf .venv-studio
  python3 -m venv .venv-studio
  source .venv-studio/bin/activate
  pip install -e ".[dev]" "langgraph-cli[inmem]"

  langgraph dev   # then open the printed Studio URL (localhost:2024 backend)
  ```

  Local dev mode needs **no LangGraph Platform deployment** — that's only for
  hosted/persistent deployments later on.
