"use client";

import { useState } from "react";
import { startCall } from "../../lib/console";

export default function CampaignsPage() {
  const [phone, setPhone] = useState("+201211497586");
  const [ticketId, setTicketId] = useState("T-1001");
  const [title, setTitle] = useState("الانترنت مش شغال");
  const [category, setCategory] = useState("routers");
  const [result, setResult] = useState<any>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function go() {
    if (!phone.trim()) return setErr("Phone number is required");
    setBusy(true); setErr(""); setResult(null);
    try {
      const res: any = await startCall({
        phone: phone.trim(), ticket_id: ticketId.trim(),
        ticket_title: title.trim(), category,
      });
      setResult(res);
    } catch (e: any) { setErr(e.message); }
    finally { setBusy(false); }
  }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Call Center</h1>
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 max-w-md space-y-3">
        <h3 className="font-semibold">
          Place outbound call <span className="text-xs text-amber-400">Vonage live dial 📞</span>
        </h3>
        <div>
          <label className="text-xs text-zinc-500">Phone number *</label>
          <input value={phone} onChange={(e) => setPhone(e.target.value)}
            className="w-full bg-zinc-950 border border-zinc-800 rounded-lg px-3 py-2 text-sm" dir="ltr" />
        </div>
        <div>
          <label className="text-xs text-zinc-500">Ticket ID</label>
          <input value={ticketId} onChange={(e) => setTicketId(e.target.value)}
            className="w-full bg-zinc-950 border border-zinc-800 rounded-lg px-3 py-2 text-sm" />
        </div>
        <div>
          <label className="text-xs text-zinc-500">Ticket title (spoken in greeting)</label>
          <input value={title} onChange={(e) => setTitle(e.target.value)}
            className="w-full bg-zinc-950 border border-zinc-800 rounded-lg px-3 py-2 text-sm" dir="rtl" />
        </div>
        <div>
          <label className="text-xs text-zinc-500">KB category</label>
          <select value={category} onChange={(e) => setCategory(e.target.value)}
            className="w-full bg-zinc-950 border border-zinc-800 rounded-lg px-3 py-2 text-sm">
            <option>routers</option><option>billing</option><option>accounts</option>
          </select>
        </div>
        <button onClick={go} disabled={busy}
          className="bg-sky-600 hover:bg-sky-500 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm">
          📞 Start call
        </button>
        {err && <p className="text-red-400 text-sm">{err}</p>}
        {result && (
          <pre className="text-xs bg-zinc-950 border border-green-700 rounded-lg p-3 overflow-auto">
{JSON.stringify(result, null, 2)}
          </pre>
        )}
      </div>
    </div>
  );
}
