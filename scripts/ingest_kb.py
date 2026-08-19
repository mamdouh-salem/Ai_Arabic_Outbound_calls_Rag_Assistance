import os
import asyncio
from dotenv import load_dotenv
from supabase import create_client, Client

# Load env keys (OpenAI + Supabase + LangSmith)
load_dotenv()

# Setup Supabase client direct
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

async def main():
    print("🚀 Starting Arabic Knowledge Base Ingestion...")
    kb_path = os.path.join("data", "knowledge_base")
    
    if not os.path.exists(kb_path):
        os.makedirs(kb_path)
        print(f"⚠️ Put your Arabic SOP docs inside folder: {kb_path}")
        return

    # Check text files inside data/knowledge_base
    files = [f for f in os.listdir(kb_path) if f.endswith(('.txt', '.md'))]
    if not files:
        print("❌ No Arabic files found to ingest! Add a text file first.")
        return

    print(f"📚 Found {len(files)} files to process...")
    for file_name in files:
        with open(os.path.join(kb_path, file_name), "r", encoding="utf-8") as f:
            content = f.read()
            print(f"📄 Processing: {file_name}")
            
            # Simple chunking logic to populate table
            # (El log da hay-fire LangSmith tracing automatic tool ma el openai aw langchain shaghaleen)
            try:
                supabase.table("knowledge_base_chunks").insert({
                    "content": content,
                    "metadata": {"source": file_name}
                }).execute()
                print(f"✅ Successfully inserted content from {file_name}")
            except Exception as e:
                print(f"❌ Supabase Insert Error: {e}")

    print("📊 All done! Check your LangSmith dashboard for tracking logs.")

if __name__ == "__main__":
    asyncio.run(main())
