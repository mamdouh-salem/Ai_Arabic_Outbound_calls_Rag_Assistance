"use client";

import { useState } from "react";
import { dataQuery } from "../../lib/console";

export default function DataInsightsPage() {
  const [question, setQuestion] = useState("");
  const [sql, setSql] = useState<string | null>(null);
  const [columns, setColumns] = useState<string[]>([]);
  const [rows, setRows] = useState<Record<string, unknown>[]>([]);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function run() {
    if (!question.trim()) return;
    setBusy(true); setErr(""); setRows([]); setColumns([]); setSql(null);
    try {
      const res: any = await dataQuery(question.trim());
      setSql(res.sql);
      setColumns(res.columns ?? []);
      setRows(res.rows ?? []);
    } catch (e: any) { setErr(e.message); }
    finally { setBusy(false); }
  }

  return (
    <div className="p-8 space-y-4">
      <h1 className="text-2xl font-semibold">Data Insights</h1>
      <p className="text-sm text-zinc-600">
        Ask business-data questions in plain language — the LLM writes a validated
        read-only SQL and we run it. admin/super admin only.
      </p>
      <div className="bg-white border border-zinc-200 rounded-xl p-5 max-w-2xl space-y-3">
        <textarea value={question} onChange={(e) => setQuestion(e.target.value)} rows={2}
          dir="rtl" placeholder="اكتب سؤالك عن البيانات… مثال: اعرض كل الـ agents في الـ default workspace"
          className="w-full border border-zinc-300 rounded-lg px-3 py-2 text-sm" />
        <button onClick={run} disabled={busy}
          className="bg-black text-white px-4 py-2 rounded-lg text-sm disabled:opacity-50">
          {busy ? "Running…" : "🔍 Query the data"}
        </button>
        {sql && (
          <pre className="text-xs bg-zinc-950 text-zinc-100 rounded-lg p-3 overflow-auto">
{`-- generated SQL (validated, read-only)\n${sql}`}
          </pre>
        )}
        {err && <p className="text-red-600 text-sm">{err}</p>}
      </div>

      <div className="bg-white border border-zinc-200 rounded-xl overflow-x-auto">
        {rows.length ? (
          <>
            <p className="text-xs text-zinc-500 p-3">
              {rows.length} row(s) returned
            </p>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-zinc-500 border-b border-zinc-200 text-left">
                  {columns.map((c) => (
                    <th key={c} className="p-3 font-medium">{c}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={i} className="border-b border-zinc-100 hover:bg-zinc-50">
                    {columns.map((c) => (
                      <td key={c} className="p-3">{String(r[c] ?? "")}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        ) : (
          <p className="p-4 text-zinc-500 text-sm">Run a query to see results.</p>
        )}
      </div>
    </div>
  );
}
