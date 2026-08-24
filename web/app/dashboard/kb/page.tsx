"use client";

import { useEffect, useState } from "react";
import { supabase } from "../../supabaseClient";

type Chunk = {
  id: string;
  content: string;
  created_at: string;
};

export default function KBPage() {
  const [chunks, setChunks] = useState<Chunk[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    async function fetchChunks() {
      const { data, error } = await supabase
        .from("knowledge_base_chunks")
        .select("id, content, created_at")
        .order("created_at", { ascending: false })
        .limit(20);

      if (error) {
        setError(error.message);
      } else {
        setChunks(data || []);
      }
      setLoading(false);
    }
    fetchChunks();
  }, []);

  return (
    <div className="p-8">
      <h1 className="text-2xl font-semibold mb-6">Knowledge Base</h1>
      <button className="bg-black text-white rounded px-4 py-2 mb-6">
        + Upload Document
      </button>
      {loading && <p className="text-zinc-500">Loading...</p>}
      {error && <p className="text-red-600 text-sm">{error}</p>}
      {!loading && !error && chunks.length === 0 && (
        <div className="bg-white dark:bg-zinc-900 rounded-lg shadow p-6 text-zinc-500">
          No documents uploaded yet.
        </div>
      )}
      {chunks.length > 0 && (
        <div className="flex flex-col gap-3">
          {chunks.map((c) => (
            <div key={c.id} className="bg-white dark:bg-zinc-900 rounded-lg shadow p-4">
              <p className="text-sm text-zinc-700 dark:text-zinc-300 line-clamp-3">
                {c.content}
              </p>
              <p className="text-xs text-zinc-400 mt-2">
                {new Date(c.created_at).toLocaleDateString()}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}