"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "../../apiClient";

type Document = {
  source_name: string;
  chunk_count?: number;
};

export default function KBPage() {
  const [docs, setDocs] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    async function fetchDocs() {
      try {
        const data = await apiFetch("/kb/documents");
        setDocs(data || []);
      } catch (err: any) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }
    fetchDocs();
  }, []);

  return (
    <div className="p-8">
      <h1 className="text-2xl font-semibold mb-6">Knowledge Base</h1>
      <button className="bg-black text-white rounded px-4 py-2 mb-6">
        + Upload Document
      </button>
      {loading && <p className="text-zinc-500">Loading...</p>}
      {error && <p className="text-red-600 text-sm">{error}</p>}
      {!loading && !error && docs.length === 0 && (
        <div className="bg-white dark:bg-zinc-900 rounded-lg shadow p-6 text-zinc-500">
          No documents uploaded yet.
        </div>
      )}
      {docs.length > 0 && (
        <div className="flex flex-col gap-3">
          {docs.map((d) => (
            <div key={d.source_name} className="bg-white dark:bg-zinc-900 rounded-lg shadow p-4">
              <p className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                {d.source_name}
              </p>
              {d.chunk_count !== undefined && (
                <p className="text-xs text-zinc-400 mt-1">{d.chunk_count} chunks</p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}