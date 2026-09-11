# RAG verification report

Owner: Teammate D (Quality)
Scope: does the Arabic assistant answer what the knowledge base covers, and
refuse everything else?

## How to reproduce

```bash
python scripts/eval_rag.py --generate            # in-scope, 15 cases
python scripts/eval_rag_negative.py              # out-of-scope, 17 cases
```

Both read their datasets from `data/eval/`. The negative runner sleeps 13s
between calls (`--delay`) to stay inside the Gemini free-tier rate limit.

## In-scope results

15 questions, one per knowledge-base chunk, written in Egyptian dialect that
deliberately avoids the source documents' own wording.

| metric | result |
|---|---|
| recall@5 | 15/15 (100%) |
| recall@1 | 11/15 (73%) |
| MRR | 0.800 |
| refusal rate | 0/15 |

Per category, recall@5 is 5/5 for accounts, billing and routers.

## Out-of-scope results

17 adversarial cases. Refusal is the correct outcome for five of the seven
types; the two language cases should be answered.

| type | result | expected |
|---|---|---|
| adjacent_not_in_kb | 4/4 | refuse |
| off_topic | 3/3 | refuse |
| data_extraction | 3/3 | refuse |
| prompt_injection | 3/3 | refuse |
| malformed | 2/2 | refuse |
| language_msa | 1/1 | answer |
| language_english | 1/1 | answer |

**17/17 correct. Zero internal-detail leaks. Zero non-Arabic replies.**

The prompt-injection set includes one English-language attempt asking for the
system prompt in English; it was refused, and the refusal came back in Arabic.

## Observations

**MRR regressed 0.833 -> 0.800** between the previous baseline and the current
retriever code. Recall is unaffected, so this is a ranking change rather than a
correctness one, but it is worth knowing before anyone tunes further.

**recall@1 is 73%.** Near-misses are semantically adjacent SOPs — a question
about entering the router settings surfaces the factory-reset document first.
Harmless at k=5, but lowering `RAG_TOP_N_AFTER_RERANK` for latency would cost
accuracy.

**An English question receives an Arabic answer.** Reasonable for an Egyptian
phone agent, but it is not recorded anywhere as a deliberate decision. Should
be confirmed and documented either way.

**The category filter costs more than it buys.** Dropping it keeps recall at
100% and moves MRR only 0.833 -> 0.786, yet `match_chunks` requires it — so a
wrong category from the intent classifier returns zero rows and forces a
refusal. A soft boost would be safer than a hard filter.

**Gemini free tier is 20 generations per day and 5 per minute, shared across
the whole project.** Not per developer. A single full evaluation run consumes
most of a day's quota, and any teammate exercising the app draws from the same
bucket. This blocks demos and needs a paid plan or separate keys.

## What this rules out

The four calls in the old `call_reports.jsonl` all ended in the grounding
fallback, which had been read as a RAG failure. Refusal rate on real
knowledge-base questions is 0/15, so retrieval and generation were not the
cause. Those turns were complaints ("لسه المشكلة ما اتحلتش"), not questions —
no SOP answers "it is still broken", so grounding refused correctly. The defect
is upstream in `graph/edges.route_after_kb`, documented as xfail in
`tests/unit/test_call_outcome_and_routing.py`.
