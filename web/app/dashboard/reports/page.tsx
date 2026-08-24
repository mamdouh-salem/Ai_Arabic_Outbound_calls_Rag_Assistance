"use client";

import { useEffect, useState } from "react";
import { getCalls } from "../../lib/console";

export default function ReportsPage() {
  const [stats, setStats] = useState<Record<string, number>>({});
  useEffect(() => {
    getCalls().then((rows: any[]) => {
      const out: Record<string, number> = {
        "Total calls": rows.length,
        Resolved: rows.filter((r) => r.call_outcome === "resolved").length,
        Escalated: rows.filter((r) => r.escalated).length,
        Unresolved: rows.filter((r) => r.call_outcome === "unresolved").length,
        "Not connected": rows.filter((r) => r.call_outcome === "not_connected").length,
        "KB assisted": rows.filter((r) => r.kb_answer_given).length,
      };
      setStats(out);
    }).catch(() => {});
  }, []);

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Reports — First Call Resolution</h1>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
        {Object.entries(stats).map(([k, v]) => (
          <div key={k} className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
            <div className="text-3xl font-bold text-sky-400">{v}</div>
            <div className="text-xs text-zinc-500 mt-1">{k}</div>
          </div>
        ))}
      </div>
      <p className="text-xs text-zinc-500">
        Full per-call details live in the Calls tab. Teammate D: FCR trend charts land here next.
      </p>
    </div>
  );
}
