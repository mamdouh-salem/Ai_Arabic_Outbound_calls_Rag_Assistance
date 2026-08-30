"use client";

import { useEffect, useState } from "react";
import { getCalls } from "../../lib/console";

const STATUS: Record<string, string> = {
  answered: "bg-green-100 text-green-700",
  dialing: "text-zinc-500",
  ringing: "bg-amber-100 text-amber-700",
  busy: "bg-red-100 text-red-700",
  rejected: "bg-red-100 text-red-700",
  failed: "bg-red-100 text-red-700",
  timeout: "bg-amber-100 text-amber-700",
};

export default function CallsPage() {
  const [rows, setRows] = useState<any[]>([]);
  const [err, setErr] = useState("");
  useEffect(() => {
    getCalls().then(setRows).catch((e) => setErr(e.message));
  }, []);

  return (
    <div className="p-8 space-y-4">
      <h1 className="text-2xl font-semibold">Calls</h1>
      {err && <p className="text-red-600 text-sm">{err}</p>}
      <div className="bg-white border border-zinc-200 rounded-xl overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-zinc-500 border-b border-zinc-200 text-left">
              <th className="p-3">Date</th><th className="p-3">Call ID</th>
              <th className="p-3">Status</th><th className="p-3">Duration</th>
              <th className="p-3">Outcome</th><th className="p-3">Intent</th>
              <th className="p-3">KB?</th><th className="p-3">Esc</th>
              <th className="p-3">Transcript</th><th className="p-3">Summary</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-b border-zinc-100 align-top hover:bg-zinc-50">
                <td className="p-3 whitespace-nowrap">
                  {r.started_at ? new Date(r.started_at).toLocaleString() : "—"}
                </td>
                <td className="p-3 font-mono text-xs">{(r.vonage_call_id ?? r.id ?? "").slice(0, 10)}</td>
                <td className="p-3">
                  <span className={`px-2 py-0.5 rounded text-xs ${STATUS[r.call_status] ?? "text-zinc-400"}`}>
                    {r.call_status ?? "—"}
                  </span>
                </td>
                <td className="p-3 whitespace-nowrap">
                  {r.duration_seconds != null
                    ? `${Math.floor(r.duration_seconds / 60)}m ${r.duration_seconds % 60}s` : "—"}
                </td>
                <td className="p-3">{r.call_outcome ?? "—"}</td>
                <td className="p-3">{r.intent ?? "—"}</td>
                <td className="p-3">{r.kb_answer_given ? "✅" : "—"}</td>
                <td className="p-3">{r.escalated ? "🚨" : "—"}</td>
                <td className="p-3 max-w-[200px] text-zinc-600" dir="rtl">
                  {(r.transcript ?? "").slice(0, 110)}…
                </td>
                <td className="p-3 max-w-[220px]" dir="rtl">{r.call_summary ?? "—"}</td>
              </tr>
            ))}
            {!rows.length && (
              <tr><td colSpan={10} className="p-4 text-zinc-500">No calls visible to your role.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
