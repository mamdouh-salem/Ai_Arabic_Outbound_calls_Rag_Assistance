# Voice Layer Design (STT + TTS)

Covers UC1's "Arabic Speech Recognition & Synthesis" requirement. Everything here lives under
`src/outbound_ai/voice/` and is consumed only through the ports in `voice/base.py` — no agent,
graph node or UI tab imports OpenAI or ElevenLabs directly.

Decisions locked with the project owner:

| Decision | Choice |
|---|---|
| Turn-taking | Push-to-talk button in Gradio |
| STT | OpenAI Whisper family (`gpt-4o-transcribe`), `language=ar` |
| TTS | ElevenLabs, streaming |
| Playback | Stream audio chunks as LLM tokens arrive |
| Spoken dialect | Egyptian colloquial (عامية مصرية) |
| Written Arabic | MSA (reports, escalation briefs, KB, agent co-pilot answers) |

---

## 1. Turn loop (push-to-talk)

```
┌─ AI turn ──────────────────────────────────────────────────────────────┐
│  LLM token stream ─▶ sentence chunker ─▶ TTS stream ─▶ audio queue     │
│                                                        │               │
│  Gradio streaming player ◀─────────────────────────────┘               │
│  [🎤 اضغط للتحدث] DISABLED while audio is playing                       │
└────────────────────────────────────────────────────────────────────────┘
                                   │ playback done → button ENABLED
                                   ▼
┌─ Customer turn ────────────────────────────────────────────────────────┐
│  press & hold ─▶ mic capture ─▶ release ─▶ wav 16 kHz mono             │
│                                          ─▶ STT ─▶ normalize ─▶ text   │
└────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼  graph node: intent_classifier
```

**What push-to-talk buys us:** no VAD silence tuning, no end-of-speech false triggers, and
**barge-in is structurally impossible** — the button is disabled during playback, so the AI can
never be talking while the customer is. Endpointing is an explicit user event, not a guess.

**What it costs:** it is not how a real phone call behaves. When the Twilio adapter lands, VAD
becomes mandatory. Therefore endpointing is isolated in `voice/vad.py` behind an `EndpointingPort`
even now — the push-to-talk implementation is just a `ManualEndpointing` that resolves when the
UI sends a release event. Swapping in `SileroEndpointing` later touches one binding.

---

## 2. STT — `voice/stt_whisper.py`

**Model:** `gpt-4o-transcribe` (config: `STT_MODEL`). Fallback `whisper-1` if the endpoint errors.

**Input contract:** 16 kHz, mono, 16-bit PCM WAV. Gradio's microphone yields
`(sample_rate, np.ndarray)` at the browser's rate (often 48 kHz) — `voice/audio_utils.py` owns
resampling, mono-mixing and dtype conversion. Nothing else resamples.

**Call parameters:**

| Param | Value | Why |
|---|---|---|
| `language` | `ar` | Forcing it prevents Whisper drifting to Farsi/Urdu on short noisy clips |
| `temperature` | `0` | Deterministic; we branch on this text |
| `prompt` | domain vocabulary + ticket terms | Biases decoding toward our product names, e.g. رقم التذكرة, تفعيل الخدمة, الفاتورة. Built per-call from the ticket row |
| `response_format` | `json` | We only need text + we add our own metadata |

**The `prompt` field is the cheapest accuracy win we have.** Egyptian speakers say product names in
mixed Arabic/English; without biasing, Whisper transliterates them inconsistently and the intent
classifier sees a different string every call.

**Post-processing — `normalize_arabic()`** runs before the text reaches any agent:

| Step | Example |
|---|---|
| Strip diacritics (tashkeel) | `نَعَم` → `نعم` |
| Strip tatweel | `نعـــم` → `نعم` |
| Unify alef forms `أ إ آ ٱ` → `ا` | `أيوة` → `ايوة` |
| Unify `ى` → `ي`, `ة` → `ه` (matching only) | `مشكله` ≡ `مشكلة` |
| Arabic-Indic digits `٠-٩` → `0-9` | `تذكرة رقم ١٢٣` → `123` |
| Collapse whitespace, trim | |

Two variants are kept on the turn record: `text_raw` (verbatim, goes in the transcript and the
report — QA must see what was actually said) and `text_norm` (fed to the classifier and to sparse
retrieval). **Never overwrite the raw text.**

**Failure handling** (doc requirement: *"fall-back to human agent if AI fails"*):

| Condition | Action |
|---|---|
| Empty / whitespace-only transcript | Reprompt: `معلش، مسمعتش حضرتك كويس. ممكن تعيد تاني؟` |
| Audio shorter than 300 ms | Same reprompt, does not count as a turn |
| 2 consecutive failed transcripts | Route to `routing_agent` with reason `stt_failure` |
| API error | Retry ×2 with `tenacity` exponential backoff, then `stt_failure` |

The retry counter lives in `CallState`, not in the voice layer — the voice layer stays stateless.

---

## 3. TTS — `voice/tts_elevenlabs.py`

**Model:** `eleven_flash_v2_5` for in-call turns (lowest latency), `eleven_multilingual_v2` for
pre-rendered static prompts where quality matters more than speed. Both are configurable; we run a
bake-off on Egyptian phrasing before fixing the default.

**Output format:** streaming into Gradio needs raw PCM, not MP3, because `gr.Audio(streaming=True)`
consumes `(sample_rate, np.ndarray)` tuples. `ELEVENLABS_OUTPUT_FORMAT=pcm_16000` everywhere,
including the disk cache, which is written as 16 kHz WAV. That removes the ffmpeg dependency
(`pydub` was dropped for this reason) — one audio format end to end, no codecs.

### 3.1 Streaming pipeline

```
LLM (astream)                sentence chunker              ElevenLabs stream
  "عايز"  ──┐
  " أتأكد" ─┤  buffer ──▶ flush on ، . ؟ ! \n  ──▶  "عايز أتأكد إن المشكلة اتحلت؟" ──▶ pcm chunks
  " إن"   ─┤             or on ≥ 60 chars                                              │
  ...     ─┘                                                                           ▼
                                                                             asyncio.Queue
                                                                                       │
                                                                    Gradio yields (16000, np.int16)
```

**Why chunk on sentence boundaries and not on tokens:** Arabic prosody is decided at clause level.
Feeding TTS 3-word fragments produces flat, chopped speech with audible seams. Flushing on
`، . ؟ ! \n` or at 60+ characters keeps each request long enough to sound natural while still
starting playback long before the LLM has finished.

The chunker lives in `voice/text_stream.py` (not `audio_utils.py` — it handles text, not audio):
`sentence_chunker(AsyncIterator[str]) -> AsyncIterator[str]`, pure, no I/O, testable without any
API key. `split_segments()` is the synchronous equivalent used in tests.

One implementation detail that bites: HTTP chunk boundaries do not respect PCM sample boundaries,
so a response chunk can end on an odd byte count. Reading that straight as int16 shifts every
following sample by one byte and turns the rest of the utterance into noise.
`audio_utils.PCMStreamAssembler` carries the stray byte into the next chunk.

### 3.2 Static prompt cache

Greeting, the reprompt line, the handoff line and the closing line are fixed text. They are
synthesized once and cached to `audio_cache/<sha256(text+voice+model+rate)>.wav` (gitignored).
Cache hit = **0 ms** TTS latency on the single most latency-visible moment of the call: the opening
greeting.

The greeting is only *partly* static — it interpolates the customer name and ticket ID. It is
therefore split: cached static head + short dynamic tail. First audio starts instantly while the
dynamic part synthesizes.

### 3.3 Latency budget (push-to-talk release → first audible word)

| Stage | Expected |
|---|---|
| Resample + encode WAV | 20–50 ms |
| STT round-trip | 600–1200 ms |
| Normalization + classifier (structured output, small model) | 300–600 ms |
| LLM first token | 400–800 ms |
| First sentence flushed | +150–400 ms |
| TTS first PCM chunk | 300–500 ms |
| **Total to first audio** | **~1.8–3.5 s** |

Without streaming this would be 4–7 s. The two levers if it feels slow: shrink the first sentence
the agent is prompted to emit, and cache more static openers.

---

## 4. Ports (`voice/base.py`)

Signatures only — presented for review before any file is written.

```python
class AudioChunk(BaseModel):
    pcm: np.ndarray          # int16 mono
    sample_rate: int         # 16000 canonical
    duration_ms: int

class TranscriptionResult(BaseModel):
    text_raw: str
    text_norm: str
    language: str
    duration_ms: int
    model: str

class STTPort(ABC):
    async def transcribe(
        self, audio: AudioChunk, *, vocabulary_hints: list[str] | None = None
    ) -> TranscriptionResult: ...

class TTSPort(ABC):
    async def synthesize(self, text: str) -> AudioChunk: ...
    async def stream(self, text_stream: AsyncIterator[str]) -> AsyncIterator[AudioChunk]: ...

class EndpointingPort(ABC):
    async def wait_for_end_of_speech(self) -> AudioChunk: ...
```

Adapters: `WhisperSTT(STTPort)`, `ElevenLabsTTS(TTSPort)`, `ManualEndpointing(EndpointingPort)`
(push-to-talk), later `SileroEndpointing(EndpointingPort)`.

A `FakeSTT` / `FakeTTS` pair goes in `tests/fixtures/` so the whole graph can be tested with zero
API calls and zero cost.

---

## 5. Dialect policy

| Surface | Register | Example |
|---|---|---|
| TTS spoken to customer | Egyptian colloquial | `عايز أتأكد إن المشكلة اتحلت` |
| Call agent system prompt | Egyptian colloquial, with an explicit *"لا تستخدم الفصحى"* rule | |
| Customer STT output | whatever they said — normalized for matching only | |
| Escalation brief to the human | MSA | `العميل يفيد بأن المشكلة لم تُحل بعد اتباع الخطوات` |
| RAG answers to the human agent | MSA + citations | |
| KB documents | MSA | |
| FCR report | MSA | |

**Colloquial must be enforced in the prompt, not hoped for.** GPT defaults to MSA for Arabic unless
told otherwise, and MSA out of a phone speaker sounds like a news broadcast, which kills the
"this might be a person" effect immediately. The system prompt therefore carries colloquial
few-shot examples, not just an instruction.

The intent classifier must accept both registers on input — `أيوة / ايوه / نعم / تمام / خلاص اتحلت`
all mean resolved. That list is a prompt concern, specified in `docs/03_agent_contracts.md`.

---

## 6. Open items

- Voice selection: need an ElevenLabs voice ID that handles Egyptian well. Requires listening to
  candidates — owner picks.
- `eleven_flash_v2_5` vs `eleven_multilingual_v2` on Egyptian text: bake-off before defaulting.
- Whether the customer's raw audio is retained after transcription (storage + privacy). Default
  proposal: **discard audio, keep text**, unless QA requires recordings.
