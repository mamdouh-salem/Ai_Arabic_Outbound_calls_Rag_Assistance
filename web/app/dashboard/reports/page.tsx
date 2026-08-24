"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "../../apiClient";

export default function ReportsPage() {
  const [totalCalls, setTotalCalls] = useState<number | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    async function fetchStats() {
      try {
        const data = await apiFetch("/data/query", {
          method: "POST",
          body: JSON.stringify({ table: "calls", count_only: true }),
        });
        setTotalCalls(data.count ?? data.total ?? 0);
      } catch (err: any) {
        setError(err.message);
      }
    }
    fetchStats();
  }, []);

  return (
    <div className="p-8">
      <h1 className="text-2xl font-semibold mb-6">Reports</h1>
      {error && <p className="text-red-600 text-sm mb-4">{error}</p>}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-white dark:bg-zinc-900 rounded-lg shadow p-6">
          <p className="text-zinc-500 text-sm">Total Calls</p>
          <p className="text-3xl font-semibold mt-2">{totalCalls ?? "—"}</p>
        </div>
      </div>
    </div>
  );
}