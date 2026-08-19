"""
Quick manual test for the hybrid RAG pipeline. Run from the project root:
    python scripts/test_rag_pipeline.py "سؤال هنا"
    python scripts/test_rag_pipeline.py "سؤال هنا" --category billing
"""
from __future__ import annotations

import argparse

from outbound_ai.rag.generation import generate_answer
from outbound_ai.rag.retrievers.hybrid import hybrid_search


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("question", type=str)
    parser.add_argument("--category", type=str, default=None)
    parser.add_argument("--retrieval-only", action="store_true", help="Skip generation, just show retrieved chunks")
    args = parser.parse_args()

    print(f"\n--- Retrieval (category={args.category}) ---")
    chunks = hybrid_search(args.question, category=args.category)
    for i, chunk in enumerate(chunks, start=1):
        print(f"[{i}] score={chunk.rrf_score:.4f} found_by={chunk.found_by} source={chunk.metadata.get('source')}")
        print(f"    {chunk.content[:120]}...")

    if args.retrieval_only:
        return

    print("\n--- Generation ---")
    result = generate_answer(args.question, category=args.category)
    print(f"Answer: {result['answer']}")
    print(f"Sources: {result['sources']}")


if __name__ == "__main__":
    main()
