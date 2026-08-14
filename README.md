# Multi-Agent Arabic Outbound Calls + RAG Knowledge Assistant

Arabic (Egyptian) AI voice agent that calls back customers with open tickets, verifies whether the
procedure from their previous inbound call actually resolved the issue, tries to help from the
internal knowledge base if it did not, and hands the live call over to a human customer-service
representative — who then gets a RAG co-pilot beside them.

Built from the two use cases in `docs/00_use_case.md`:
- **UC1** — AI-powered outbound follow-up calls (Arabic STT/TTS, branching dialog, FCR report).
- **UC2** — Arabic chatbot over the internal knowledge base (RAG assistant for the human agent).

## End-to-end flow

```
                    ┌──────────────────────────────────────────────────┐
                    │  Supabase: customers + tickets (open/unresolved)  │
                    └───────────────────────┬──────────────────────────┘
                                            │ campaign picks due tickets
                                            ▼
                                   ┌────────────────────┐
                                   │  Outbound Call     │  auto-dials (simulated → Twilio later)
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
| Agentic workflow | LangGraph (`StateGraph`, conditional edges, Postgres checkpointer, `interrupt` for human handoff) |
| Tracing & visualization | LangSmith |
| LLM | OpenAI GPT (fast model for in-call turns, stronger model for reporting / rerank / grounding) |
| STT | OpenAI Whisper family, Arabic |
| TTS | ElevenLabs multilingual |
| Database + vectors | Supabase Postgres + pgvector (one store: business data **and** KB chunks) |
| Retrieval | Hybrid = dense (pgvector) + sparse (Postgres full-text) fused with RRF, metadata filtering, reranking, grounding check |
| Backend | FastAPI |
| UI | Gradio |
| Telephony | Simulated adapter now; Twilio adapter behind the same port later |

## Layout

```
docs/                       design docs (architecture, data model, agent contracts, RAG design)
data/knowledge_base/        handcrafted Arabic KB source documents
data/seeds/                 seed customers / tickets
data/eval/                  ground-truth Q→answer→source pairs for RAG evaluation
db/migrations/              SQL: extensions, core tables, KB tables, indexes, hybrid search fn
db/seed/                    seed SQL
scripts/                    ingest_kb, seed_db, eval_rag, run_api, run_ui
src/outbound_ai/
  config/                   settings (pydantic-settings), logging, LangSmith tracing setup
  schemas/                  pydantic models shared across API, graph and UI
  db/                       Supabase client + repositories (the only layer that touches the DB)
  prompts/                  the LangChain harness — one module per agent, versioned separately
  agents/                   outbound_call, intent_classifier, kb_assist, routing, reporting
  rag/                      loaders, chunking, embeddings, filters, retrievers/, rerank,
                            grounding, pipeline
  voice/                    STT/TTS ports + Whisper and ElevenLabs adapters, VAD, audio utils
  telephony/                telephony port + simulated adapter (+ Twilio adapter later)
  graph/                    LangGraph state, nodes, edges, compiled graph, human handoff
  api/                      FastAPI app and routers
  ui/                       Gradio app: campaign, live call, agent desk, KB admin, reports
tests/                      unit / integration / fixtures
```

**Design rules:** `voice/` and `telephony/` are ports with adapters, so swapping the simulator for
Twilio touches no graph code. `prompts/` is separate from `agents/` so prompt engineering is
versioned and A/B-testable without editing logic. `db/repositories/` is the only place Supabase is
imported, so schema changes stay local.

## Setup

Python 3.11 (3.13+ not yet supported by parts of the stack).

```bash
uv venv --python 3.11
uv pip install -e ".[dev]"
cp .env.example .env
```

## Status

Scaffolding only. Next steps, in order:

1. Voice layer — Arabic STT/TTS design and adapters (UC1 requirement).
2. Database schema — handcrafted together (customers, tickets, calls, turns, escalations, reports).
3. Knowledge base — handcrafted Arabic SOP documents and their chunk metadata.
4. RAG pipeline — hybrid search, metadata filtering, reranking, grounding check.
5. LangGraph wiring, FastAPI, Gradio.
