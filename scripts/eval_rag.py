"""Batch evaluation harness for the RAG pipeline.

Runs every question in data/eval/rag_eval_set.jsonl through retrieval (and
optionally generation) and reports:

  recall@k      did the expected source document appear in the top-k chunks?
                if not, generation never had a chance.
  MRR           how highly did it rank? 1.0 = first hit every time.
  refusal rate  how often generation falls back to "I don't know" -- the
                message that appeared on 100% of the logged production calls.

Usage:
    python scripts/eval_rag.py                  # retrieval only, no LLM
    python scripts/eval_rag.py --generate       # also score answers
    python scripts/eval_rag.py --no-category    # test without the category filter
    python scripts/eval_rag.py -k 3
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from collections import defaultdict

EVAL_PATH = pathlib.Path(__file__).resolve().parents[1] / "data/eval/rag_eval_set.jsonl"

# Substrings that mark the grounding fallback rather than a real answer.
_REFUSAL_MARKERS = ("لا تتوفر لدي معلومات", "سيتم تحويلك")


def load_cases() -> list[dict]:
    with EVAL_PATH.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def is_refusal(answer: str) -> bool:
    return any(marker in answer for marker in _REFUSAL_MARKERS)


def source_of(chunk) -> str:
    meta = getattr(chunk, "metadata", None) or {}
    return meta.get("source", "") or ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("-k", type=int, default=5, help="cutoff for recall@k")
    parser.add_argument("--generate", action="store_true", help="also run generation")
    parser.add_argument("--no-category", action="store_true",
                        help="drop the category filter to measure its effect")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    from outbound_ai.rag.retrievers.hybrid import hybrid_search
    if args.generate:
        from outbound_ai.rag.generation import generate_answer

    cases = load_cases()
    hits = 0
    reciprocal_ranks: list[float] = []
    refusals = 0
    generated = 0
    errors: list[tuple[str, str]] = []
    per_category: dict[str, list[int]] = defaultdict(list)

    for case in cases:
        category = None if args.no_category else case["category"]
        try:
            chunks = hybrid_search(case["question"], category=category)
        except Exception as exc:  # noqa: BLE001 - report, don't abort the run
            errors.append((case["id"], f"retrieval: {exc}"))
            per_category[case["category"]].append(0)
            continue

        sources = [source_of(c) for c in chunks[: args.k]]
        expected = case["expected_source"]

        if expected in sources:
            hits += 1
            rank = sources.index(expected) + 1
            reciprocal_ranks.append(1.0 / rank)
            per_category[case["category"]].append(1)
            status = f"HIT  @{rank}"
        else:
            reciprocal_ranks.append(0.0)
            per_category[case["category"]].append(0)
            status = "MISS   "

        line = f"[{status}] {case['id']}  expected={expected}"
        if args.verbose or expected not in sources:
            line += f"\n           got: {sources}"
        print(line)

        if args.generate:
            try:
                result = generate_answer(case["question"], category=category)
                answer = result.get("answer", "")
                generated += 1
                if is_refusal(answer):
                    refusals += 1
                    print(f"           REFUSED: {answer[:80]}")
                elif args.verbose:
                    print(f"           answer: {answer[:120]}")
            except Exception as exc:  # noqa: BLE001
                errors.append((case["id"], f"generation: {exc}"))

    total = len(cases)
    print("\n" + "=" * 62)
    print(f"cases            {total}")
    print(f"category filter  {'off' if args.no_category else 'on'}")
    print(f"recall@{args.k}         {hits}/{total}  ({hits / total:.0%})")
    print(f"MRR              {sum(reciprocal_ranks) / total:.3f}")
    if args.generate and generated:
        print(f"refusal rate     {refusals}/{generated}  ({refusals / generated:.0%})")
    print("-" * 62)
    for cat, results in sorted(per_category.items()):
        print(f"  {cat:<10} recall@{args.k} {sum(results)}/{len(results)}")
    if errors:
        print("-" * 62)
        for case_id, msg in errors:
            print(f"  ERROR {case_id}: {msg}")
    print("=" * 62)

    return 0


if __name__ == "__main__":
    sys.exit(main())
