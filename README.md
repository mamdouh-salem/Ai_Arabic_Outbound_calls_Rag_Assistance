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

## Auth & multi-tenancy setup (Phase 2 — branch `oxAlpha`)

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
| **Super admin** | Platform-wide | Create/suspend workspaces, manage billing, assign workspace admins. No routine access to any single workspace's customer data. |
| **Admin** | One workspace | Manage users within their workspace, upload/edit/delete KB documents, configure campaigns, view all reports and call logs for their workspace. |
| **User (CSR/agent)** | One workspace | Take over escalated calls, use the RAG co-pilot at the agent desk, view tickets assigned to them. Cannot upload/delete KB documents or manage other users. |

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

## Status

**Done:**
- Project scaffolding, configuration, Arabic normalization
- Voice layer ports (`STTPort` / `TTSPort` / `EndpointingPort`) + Whisper, ElevenLabs, and
  push-to-talk adapters, streaming sentence chunker, static prompt cache, fakes for testing.
  35 unit tests, no network.
- Database schema — Supabase tables for `customers`, `tickets`, `knowledge_base_chunks`
  (embedding `vector(768)`, `metadata jsonb` for category, `fts_tokens tsvector`), seeded with
  test data across `accounts` / `routers` / `billing`
- Knowledge base — handcrafted Arabic SOP documents, ingested with metadata
- RAG pipeline — hybrid search (`match_chunks` SQL function: dense pgvector + sparse full-text,
  fused with RRF), metadata category filtering, local embeddings, context building, grounded
  generation. Generation provider is pluggable (local Qwen2.5-7B / OpenAI / Gemini) via one
  config value, no code changes needed to swap
- LangGraph skeleton — `state`/`edges`/`nodes`/`build`/`deps` wired with dependency injection
  (voice ports, KB retrieval, intent classification all injected, not hardcoded), compiled graph
  with conditional routing (`outbound_call → intent_classifier → kb_assist/routing → reporting`)
- LangSmith tracing — confirmed working end-to-end, traces visible per-node
- `agents/intent_classifier.py` and `agents/kb_assist.py` — implemented and proven against a real
  LLM (Gemini) and real Supabase retrieval, not just fakes; full run verified correct
  (intent classification → grounded retrieval → generated Arabic answer → correct call outcome)
- Resolved/unresolved classification bug fixed (state-node logic error, not a transcription issue)
- LangGraph node diagram generation via `compiled_graph.get_graph().draw_mermaid_png()`

**In progress / next steps, roughly in order:**
1. **Auth** — DONE on `oxAlpha`: multi-tenancy schema + RLS (003 migration), JWT
   middleware, role guards, `/health/auth` probe, 26 unit tests. Remaining:
   sign-up/login API endpoints, auto-profile trigger registration, frontend auth screens.
2. **Multi-tenancy schema** — `workspaces` + `users`/`workspace_members` tables, `workspace_id`
   threaded through `customers`/`tickets`/`knowledge_base_chunks`, RLS policies, role checks.
3. **RAG document upload + citations** — ingestion API endpoint, citation metadata surfaced
   through generation, frontend rendering of sources.
4. **Voice AI dialect fixes** — swap in an Egyptian-tuned Whisper checkpoint, tighten Egyptian
   colloquial prompting in `prompts/`, pin/validate ElevenLabs Egyptian voices (or evaluate an
   Arabic-first TTS alternative).
5. **`orchestration/` call queue** — campaign scheduling, concurrency limits, retries, webhook
   idempotency, sitting above the LangGraph rather than inside it.
6. **Vonage telephony adapter** — concrete implementation of the telephony/voice ports against
   real Vonage Voice API calls (JWT auth, NCCO answer webhook, event webhook).
7. **PostgreSQL-backed LangGraph checkpointer** — replaces in-process `MemorySaver`; required for
   the call queue and human-handoff `interrupt()` to survive restarts/retries.
8. **`agents/routing.py`** — real escalation/handoff logic, replacing the current stub.
9. **`agents/outbound_call.py`** and **`agents/reporting.py`** — split out of `graph/nodes.py`
   into their own agent modules with dedicated, versioned prompts.
10. **Real web frontend (`web/`)** — React/Next.js, replacing Gradio as the product UI.
11. **Local Qwen2.5-7B generation path** — implemented in `common/local_llm.py` but not yet
    verified end-to-end; Gemini remains the active provider for dev/testing meanwhile.
