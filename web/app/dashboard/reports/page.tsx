"use client";

import { useEffect, useState } from "react";
import { getCalls } from "../../lib/console";

export default function ReportsPage() {
  const [stats, setStats] = useState<Record<string, number>>({});
  useEffect(() => {
    getCalls().then((rows: any[]) => {
      setStats({
        "Total calls": rows.length,
        Resolved: rows.filter((r) => r.call_outcome === "resolved").length,
        Escalated: rows.filter((r) => r.escalated).length,
        Unresolved: rows.filter((r) => r.call_outcome === "unresolved").length,
        "Not connected": rows.filter((r) => r.call_outcome === "not_connected").length,
        "KB assisted": rows.filter((r) => r.kb_answer_given).length,
      });
    }).catch(() => {});
  }, []);

  return (
    <div className="p-8 space-y-4">
      <h1 className="text-2xl font-semibold">Reports — First Call Resolution</h1>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
        {Object.entries(stats).map(([k, v]) => (
          <div key={k} className="bg-white border border-zinc-200 rounded-xl p-5">
            <div className="text-3xl font-bold">{v}</div>
            <div className="text-xs text-zinc-500 mt-1">{k}</div>
          </div>
        ))}
      </div>
      <p className="text-xs text-zinc-500">
        Full per-call details live in the Calls tab.
      </p>
    </div>
  );
}
