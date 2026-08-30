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
    <div className="p-8 space-y-4">
      <h1 className="text-2xl font-semibold">Call Center</h1>
      <div className="bg-white border border-zinc-200 rounded-xl p-5 max-w-md space-y-3">
        <h3 className="font-semibold">
          Place outbound call <span className="text-xs text-zinc-500">Vonage live dial 📞</span>
        </h3>
        <div>
          <label className="text-xs text-zinc-500">Phone number *</label>
          <input value={phone} onChange={(e) => setPhone(e.target.value)}
            className="w-full border border-zinc-300 rounded-lg px-3 py-2 text-sm" dir="ltr" />
        </div>
        <div>
          <label className="text-xs text-zinc-500">Ticket ID</label>
          <input value={ticketId} onChange={(e) => setTicketId(e.target.value)}
            className="w-full border border-zinc-300 rounded-lg px-3 py-2 text-sm" />
        </div>
        <div>
          <label className="text-xs text-zinc-500">Ticket title (spoken in greeting)</label>
          <input value={title} onChange={(e) => setTitle(e.target.value)}
            className="w-full border border-zinc-300 rounded-lg px-3 py-2 text-sm" dir="rtl" />
        </div>
        <div>
          <label className="text-xs text-zinc-500">KB category</label>
          <select value={category} onChange={(e) => setCategory(e.target.value)}
            className="w-full border border-zinc-300 rounded-lg px-3 py-2 text-sm">
            <option>routers</option><option>billing</option><option>accounts</option>
          </select>
        </div>
        <button onClick={go} disabled={busy}
          className="bg-black text-white px-4 py-2 rounded-lg text-sm disabled:opacity-50">
          📞 Start call
        </button>
        {err && <p className="text-red-600 text-sm">{err}</p>}
        {result && (
          <pre className="text-xs bg-zinc-950 text-zinc-100 border border-zinc-800 rounded-lg p-3 overflow-auto">
{JSON.stringify(result, null, 2)}
          </pre>
        )}
      </div>
    </div>
  );
}
