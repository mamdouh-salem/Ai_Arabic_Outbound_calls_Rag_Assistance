"use client";

import { useEffect, useState } from "react";
import { supabase } from "../../supabaseClient";

type Call = {
  id: string;
  customer_id: string;
  call_outcome: string | null;
  intent: string | null;
  created_at: string;
};

export default function CallsPage() {
  const [calls, setCalls] = useState<Call[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    async function fetchCalls() {
      const { data, error } = await supabase
        .from("calls")
        .select("id, customer_id, call_outcome, intent, created_at")
        .order("created_at", { ascending: false })
        .limit(50);

      if (error) {
        setError(error.message);
      } else {
        setCalls(data || []);
      }
      setLoading(false);
    }
    fetchCalls();
  }, []);

  return (
    <div className="p-8">
      <h1 className="text-2xl font-semibold mb-6">Live Calls</h1>
      {loading && <p className="text-zinc-500">Loading...</p>}
      {error && <p className="text-red-600 text-sm">{error}</p>}
      <div className="bg-white dark:bg-zinc-900 rounded-lg shadow overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-zinc-50 dark:bg-zinc-800 text-left text-zinc-500">
            <tr>
              <th className="p-3">Customer ID</th>
              <th className="p-3">Intent</th>
              <th className="p-3">Outcome</th>
              <th className="p-3">Time</th>
            </tr>
          </thead>
          <tbody>
            {!loading && calls.length === 0 && (
              <tr>
                <td colSpan={4} className="p-6 text-center text-zinc-400">
                  No calls yet.
                </td>
              </tr>
            )}
            {calls.map((c) => (
              <tr key={c.id} className="border-t border-zinc-100 dark:border-zinc-800">
                <td className="p-3">{c.customer_id}</td>
                <td className="p-3">{c.intent ?? "—"}</td>
                <td className="p-3">{c.call_outcome ?? "—"}</td>
                <td className="p-3">{new Date(c.created_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}