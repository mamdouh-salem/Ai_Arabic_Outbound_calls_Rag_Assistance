from dotenv import load_dotenv
import os

load_dotenv()

key = os.environ.get("LANGCHAIN_API_KEY", "")
print(f"Key length: {len(key)}")
print(f"Key starts with: {key[:12]!r}")
print(f"Key ends with:   {key[-8:]!r}")
print(f"Has leading/trailing whitespace: {key != key.strip()}")

from langsmith import Client

client = Client()
runs = list(client.list_runs(project_name="outbound-ai-arabic", limit=5))
print(f"Found {len(runs)} runs")
