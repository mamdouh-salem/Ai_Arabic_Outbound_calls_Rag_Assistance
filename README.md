# Multi-Agent Arabic Outbound Calls + RAG Knowledge Assistant

Arabic (Egyptian) AI voice agent that calls back customers with open tickets, verifies whether the
procedure from their previous inbound call actually resolved the issue, tries to help from the
internal knowledge base if it did not, and hands the live call over to a human customer-service
representative — who then gets a RAG co-pilot beside them.

Built from the two use cases in `docs/00_use_case.md`:
- **UC1** — AI-powered outbound follow-up calls (Arabic STT/TTS, branching dialog, FCR report).
- **UC2** — Arabic chatbot over the internal knowledge base (RAG assistant for the human agent).

Not a customer-facing SaaS product — no end-user sign-in. The agent places calls only when
triggered from open tickets (manually or by a scheduled campaign script); the Gradio UI is an
internal ops console, not a public app.

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
| STT | OpenAI Whisper family, Arabic |
| TTS | ElevenLabs multilingual |
| Database + vectors | Supabase Postgres + pgvector (one store: business data **and** KB chunks) |
| Retrieval | Hybrid = dense (pgvector, `vector(768)`) + sparse (Postgres full-text) fused with RRF, metadata (`jsonb`) category filtering |
| Backend | FastAPI |
| UI | Gradio |
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
  prompts/                  the LangChain harness — one module per agent, versioned separately
  agents/                   intent_classifier, kb_assist done; outbound_call, routing, reporting pending
  rag/                      loaders, chunking, embeddings, filters, retrievers/, rerank,
                            grounding, pipeline, generation
  voice/                    STT/TTS ports + Whisper and ElevenLabs adapters, VAD, audio utils
  telephony/                telephony port + simulated adapter (+ Vonage adapter pending)
  graph/                    LangGraph state, nodes, edges, deps (DI), compiled graph
  api/                      FastAPI app and routers (not started)
  ui/                       Gradio app: campaign, live call, agent desk, KB admin, reports (not started)
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

**Not yet done — next steps, roughly in order:**
1. **Vonage telephony adapter** — concrete implementation of the telephony/voice ports against
   real Vonage Voice API calls (JWT auth, NCCO answer webhook, event webhook). Currently only the
   simulated/fake adapters exist; this is what turns the graph into something that can place an
   actual phone call.
2. **`agents/routing.py`** — real escalation/handoff logic. Currently a stub that just sets
   `escalated: True` with a hardcoded reason; needs to actually transfer the live call to a human
   agent once Vonage is wired in.
3. **`agents/outbound_call.py`** and **`agents/reporting.py`** — currently inlined directly in
   `graph/nodes.py` rather than split into their own agent modules with dedicated prompts.
4. **PostgreSQL-backed LangGraph checkpointer** — currently `MemorySaver` (in-process, lost on
   restart). Needed before the human-handoff `interrupt()` can reliably survive a process
   boundary or restart.
5. **FastAPI backend** — not started.
6. **Gradio UI** (campaign trigger, live call view, agent desk, KB admin, reports) — not started.
7. **Local Qwen2.5-7B generation path** — implemented in `common/local_llm.py` but not yet
   verified end-to-end (download in progress; Gemini is the active provider for dev/testing in
   the meantime, swappable back via `GENERATION_PROVIDER=local`).
