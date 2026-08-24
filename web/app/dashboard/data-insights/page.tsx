"use client";

import { useState } from "react";
import { dataQuery } from "../../lib/console";

export default function DataInsightsPage() {
  const [question, setQuestion] = useState("");
  const [sql, setSql] = useState<string | null>(null);
  const [rows, setRows] = useState<any[]>([]);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function run() {
    if (!question.trim()) return;
    setBusy(true); setErr(""); setRows([]); setSql(null);
    try {
      const res: any = await dataQuery(question.trim());
      setSql(res.sql);
      setRows(res.rows ?? []);
    } catch (e: any) { setErr(e.message); }
    finally { setBusy(false); }
  }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Data Insights</h1>
      <p className="text-xs text-zinc-500">
        Ask business-data questions in plain language — the LLM writes a validated
        read-only SQL and we run it. admin/super admin only.
      </p>
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 max-w-2xl space-y-3">
        <textarea value={question} onChange={(e) => setQuestion(e.target.value)} rows={2}
          dir="rtl" placeholder="اكتب سؤالك عن البيانات… مثال: آخر 5 مكالمات متحوّلة"
          className="w-full bg-zinc-950 border border-zinc-800 rounded-lg px-3 py-2 text-sm" />
        <button onClick={run} disabled={busy}
          className="bg-sky-600 hover:bg-sky-500 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm">
          {busy ? "Running…" : "🔍 Query the data"}
        </button>
        {sql && (
          <pre className="text-xs bg-zinc-950 border border-zinc-800 rounded-lg p-3 overflow-auto">
{`-- generated SQL (validated, read-only)\n${sql}`}
          </pre>
        )}
        {err && <p className="text-red-400 text-sm">{err}</p>}
      </div>
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-x-auto">
        <table className="w-full text-sm">
          <tbody>
            {rows.length ? Object.keys(rows[0]).map((c) => (
              <tr key={c} className="border-b border-zinc-800/60">
                <td className="p-2 font-mono text-xs text-zinc-400 w-48">{c}</td>
                <td className="p-2 font-mono text-xs">{String(rows[0][c])}</td>
              </tr>
            )) : <tr><td className="p-4 text-zinc-500">Run a query to see results (first-row preview).</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
