"use client";

import { useEffect, useState } from "react";
import { supabase } from "../../supabaseClient";

export default function ReportsPage() {
  const [totalCalls, setTotalCalls] = useState<number | null>(null);
  const [escalated, setEscalated] = useState<number | null>(null);
  const [resolved, setResolved] = useState<number | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    async function fetchStats() {
      const { count: total, error: e1 } = await supabase
        .from("calls")
        .select("*", { count: "exact", head: true });

      const { count: escalatedCount, error: e2 } = await supabase
        .from("calls")
        .select("*", { count: "exact", head: true })
        .eq("escalated", true);

      const { count: resolvedCount, error: e3 } = await supabase
        .from("calls")
        .select("*", { count: "exact", head: true })
        .eq("call_outcome", "resolved");

      if (e1 || e2 || e3) {
        setError((e1 || e2 || e3)?.message || "Error loading stats");
      } else {
        setTotalCalls(total ?? 0);
        setEscalated(escalatedCount ?? 0);
        setResolved(resolvedCount ?? 0);
      }
    }
    fetchStats();
  }, []);

  const fcr =
    totalCalls && totalCalls > 0 && resolved !== null
      ? `${Math.round((resolved / totalCalls) * 100)}%`
      : "—";
  const escalationRate =
    totalCalls && totalCalls > 0 && escalated !== null
      ? `${Math.round((escalated / totalCalls) * 100)}%`
      : "—";

  return (
    <div className="p-8">
      <h1 className="text-2xl font-semibold mb-6">Reports</h1>
      {error && <p className="text-red-600 text-sm mb-4">{error}</p>}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-white dark:bg-zinc-900 rounded-lg shadow p-6">
          <p className="text-zinc-500 text-sm">First Call Resolution</p>
          <p className="text-3xl font-semibold mt-2">{fcr}</p>
        </div>
        <div className="bg-white dark:bg-zinc-900 rounded-lg shadow p-6">
          <p className="text-zinc-500 text-sm">Total Calls</p>
          <p className="text-3xl font-semibold mt-2">{totalCalls ?? "—"}</p>
        </div>
        <div className="bg-white dark:bg-zinc-900 rounded-lg shadow p-6">
          <p className="text-zinc-500 text-sm">Escalation Rate</p>
          <p className="text-3xl font-semibold mt-2">{escalationRate}</p>
        </div>
      </div>
    </div>
  );
}