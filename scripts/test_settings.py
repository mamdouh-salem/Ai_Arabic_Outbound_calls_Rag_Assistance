"""
Quick standalone check for src/outbound_ai/config/settings.py.
Run from the project root: python test_settings.py
(or drop it into scripts/ and run: python scripts/test_settings.py)
"""
import os
import sys

# adjust this import to match wherever settings.py actually lives in your repo
from outbound_ai.config.settings import get_settings


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    return condition


def main():
    all_ok = True

    settings = get_settings()

    all_ok &= check(
        "telephony_provider is 'vonage' (not crashing on Literal)",
        settings.telephony_provider == "vonage",
    )
    all_ok &= check(
        "vonage_application_id loaded from .env",
        bool(settings.vonage_application_id),
    )
    all_ok &= check(
        "vonage_private_key_full_path resolves to an existing file",
        settings.vonage_private_key_full_path.exists(),
    )
    all_ok &= check(
        "langsmith_project loaded via LANGCHAIN_PROJECT alias",
        settings.langsmith_project == "outbound-ai-arabic",
    )
    all_ok &= check(
        "langsmith_api_key loaded via LANGCHAIN_API_KEY alias",
        settings.langsmith_api_key is not None,
    )

    # the part that actually matters for tracing to fire at runtime:
    # did export_tracing_env() really reach os.environ?
    all_ok &= check(
        "os.environ['LANGCHAIN_TRACING_V2'] set after get_settings()",
        os.environ.get("LANGCHAIN_TRACING_V2") == "true",
    )
    all_ok &= check(
        "os.environ['LANGCHAIN_API_KEY'] set after get_settings()",
        bool(os.environ.get("LANGCHAIN_API_KEY")),
    )
    all_ok &= check(
        "os.environ['LANGCHAIN_PROJECT'] set after get_settings()",
        os.environ.get("LANGCHAIN_PROJECT") == "outbound-ai-arabic",
    )

    all_ok &= check(
        "openai_embedding_dim matches embedding model (3-large -> 3072)",
        settings.openai_embedding_dim == 3072
        if "large" in settings.openai_embedding_model
        else settings.openai_embedding_dim == 1536,
    )

    print()
    if all_ok:
        print("All checks passed — settings.py is wired correctly.")
        sys.exit(0)
    else:
        print("Some checks failed — see FAIL lines above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
