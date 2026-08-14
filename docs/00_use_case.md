# Source Requirements

Verbatim distillation of `AI-Powered Outbound Calls (Arabic).docx` (kept in this folder).
This file is the requirements baseline — design decisions live in the other `docs/` files.

---

## Use Case 1: AI-Powered Outbound Calls (Arabic)

### 1. Objective
- Ensure customers have correctly followed procedures reviewed on their prior inbound call.
- Boost First Call Resolution (FCR) KPI by proactively verifying compliance.
- Automate routine follow-up calls, freeing live agents for complex issues.
- Generate a documented "First Call Resolutions" report for quality assurance.

### 2. Functional & Technical Requirements

**Arabic Speech Recognition & Synthesis**
- High-quality STT in Egyptian (and Modern Standard) Arabic.
- Natural-sounding TTS in Arabic dialect(s).

**Call Orchestration**
- Integration with the telephony provider (Twilio, Vonage, or on-prem PBX).
- Retry logic, fall-back to human agent if AI fails.

**Conversation Logic**
- Dynamic script that pulls in details from the previous inbound call (ticket ID, procedure steps).
- Branching dialogs based on customer responses (yes / no / uncertain / request live agent).

**Data & Reporting**
- Real-time logging of call results, durations, and resolutions.
- Automatic generation of the "First Call Resolutions" article/report.

### 3. Proposed Architecture (as given)

```
[CRM / Inbound Call Records]
            │
            ▼
  [Call Scheduler & API] ──▶ [AI Call Engine]
           │                    • STT (Arabic Whisper)
           │                    • NLU & Dialogue (LLM)
           │                    • TTS (Arabic Neural Voices)
           ▼
 [Telephony Provider API] ──▶ [Customer Phone]
           │
           ▼
[Logging & Reporting DB] ──▶ [FCR Dashboard / "First Call Resolutions" Report]
```

### 4. Workflow Steps
1. Fetch list of customers flagged for follow-up (e.g. incomplete steps).
2. Schedule outbound call slot via telephony API.
3. Dial customer, play dynamic TTS greeting in Arabic:
   > صباح الخير، معك نظام المتابعة من شركة XYZ. نتأكد الآن من استكمال الإجراءات التي ناقشناها في مكالمتك الأخيرة…
4. Listen to customer's responses, transcribe via STT.
5. Validate step completion; if "نعم" mark as resolved; if "لا" or "غير متأكد" prompt further
   assistance or transfer to live agent.
6. Log call outcome and duration.
7. Compile resolved calls into the "First Call Resolutions" article — auto-formatted for the
   quality team.

### 5. Key Success Metrics
- **FCR Rate** — target ≥ 90% on first outbound follow-up.
- **Call Completion** — % of calls fully handled by AI without handoff.
- **Average Handle Time** — time per follow-up call vs. live-agent baseline.
- **Report Accuracy** — % of AI-generated resolutions matching manual audit.

---

## Use Case 2: Arabic Chatbot Integrated with Internal Knowledge Base

### 1. Objective
- Empower agents with instant, accurate answers drawn from proprietary documentation.
- Reduce average handle time (AHT) and training ramp-up with an "always-on" Arabic assistant.

### 2. Requirements
- RAG setup to query the internal KB (PDFs, Wiki, SOPs).
- Arabic language understanding for dialect nuance and formal registers.
- Agent UI integration (widget in the contact-center desktop).
- Access controls & audit trail to secure proprietary data.

### 3. Proposed Architecture (as given)

```
[Internal KB Storage]
    ├─ Documents (PDF / Word / Wiki)
    └─ Structured Data (DB)
            │
   (1) Preprocessing & Embeddings ──▶ [Vector DB]
            │
   (2) Agent Query ──▶ [Chat Interface]
            │            • LLM
            │            • RAG: retrieves top K docs
            ▼
      [Answer + Source Snippets] ──▶ [Agent Desktop / Chat UI]
            │
      [Logging / Feedback Loop]
```

### 4. Workflow Steps
1. Ingest & embed internal docs nightly (convert to text, chunk, embed in vector DB).
2. Agent types a query in Arabic, e.g.
   > ما هي خطوات تحديث بيانات العميل في النظام الداخلي؟
3. RAG pipeline retrieves relevant passages.
4. LLM crafts a concise, cited answer in Arabic, e.g.
   > يمكنك تحديث بيانات العميل عبر الدخول إلى… (المصدر: قسم العمليات، صفحة 12)
5. Agent reviews, shares with customer, or asks a follow-up.
6. Feedback (thumbs up/down) feeds back into retraining / prompt-tuning.

### 5. Success Metrics
- **Time-to-Answer** — average latency from query to answer (< 2 seconds).
- **Agent Satisfaction** — surveys on answer accuracy (≥ 4.5/5).
- **Usage Rate** — % of inquiries handled by bot vs. manual search.
- **Knowledge Coverage** — % of KB with up-to-date embeddings.

---

## Deviations from the document (agreed)

| Doc says | We do | Why |
|---|---|---|
| CRM / inbound call records | Handcrafted Supabase schema | Manager ruled out Salesforce/HubSpot |
| Pinecone vector DB | Supabase pgvector | One store for business data + chunks; hybrid search in SQL |
| Telephony provider from day 1 | Simulated telephony adapter first, Twilio adapter behind the same port | Demoable without a phone number; no rewrite later |
| Top-K retrieval | Hybrid (dense + full-text, RRF) + metadata filtering + reranking + grounding check | Higher precision, required by the project brief |
| Agent-only RAG | Bot self-serves from KB in-call, then escalates with a RAG brief | Covers UC1 and UC2 in one flow |
