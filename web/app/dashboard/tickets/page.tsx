"use client";

import { useEffect, useState } from "react";
import { useIdentity } from "../layout";
import { callTicket, getTickets } from "../../lib/console";

type Ticket = {
  id: string;
  title: string;
  status: string;
  kb_category: string;
  assigned_to: string | null;
  customer_name: string | null;
  customer_phone: string | null;
};

export default function TicketsPage() {
  const me = useIdentity();
  const [rows, setRows] = useState<Ticket[]>([]);
  const [err, setErr] = useState("");

  async function load() {
    try { setRows((await getTickets()) as Ticket[]); } catch (e: any) { setErr(e.message); }
  }
  useEffect(() => { if (me) load(); }, [me]);

  async function call(id: string) {
    if (!confirm("Place the AI call to this ticket's customer now?")) return;
    try {
      const res: any = await callTicket(id);
      alert(`📞 Call placed to ${res.phone} — pick up!`);
    } catch (e: any) { alert(e.message); }
  }

  const canCall = me?.role === "admin" || me?.role === "super_admin";

  return (
    <div className="p-8 space-y-4">
      <h1 className="text-2xl font-semibold">Tickets</h1>
      <p className="text-sm text-zinc-600">
        agent → only tickets assigned to you · admin → whole workspace · super admin → everything
      </p>
      {err && <p className="text-red-600 text-sm">{err}</p>}
      <div className="bg-white border border-zinc-200 rounded-xl overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-zinc-500 border-b border-zinc-200 text-left">
              <th className="p-3">ID</th><th className="p-3">Title</th>
              <th className="p-3">Customer</th><th className="p-3">Phone</th>
              <th className="p-3">Status</th><th className="p-3">Category</th>
              <th className="p-3">Assigned</th>{canCall && <th className="p-3"></th>}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-b border-zinc-100 hover:bg-zinc-50">
                <td className="p-3 font-mono text-xs">{r.id.slice(0, 8)}</td>
                <td className="p-3" dir="rtl">{r.title}</td>
                <td className="p-3" dir="rtl">{r.customer_name ?? "—"}</td>
                <td className="p-3 font-mono text-xs" dir="ltr">{r.customer_phone ??
                  <span className="text-red-600">no phone ⚠️</span>}</td>
                <td className="p-3">{r.status}</td>
                <td className="p-3">{r.kb_category ?? "—"}</td>
                <td className="p-3 text-zinc-500">{r.assigned_to ? r.assigned_to.slice(0, 8) : "unassigned"}</td>
                {canCall && (
                  <td className="p-3">
                    {r.customer_phone ? (
                      <button onClick={() => call(r.id)}
                        className="bg-black text-white text-xs px-3 py-1.5 rounded-lg hover:bg-zinc-700">
                        📞 Call
                      </button>
                    ) : (
                      <button disabled className="text-xs px-3 py-1.5 rounded-lg bg-zinc-100 text-zinc-400 cursor-not-allowed">
                        📞
                      </button>
                    )}
                  </td>
                )}
              </tr>
            ))}
            {!rows.length && (
              <tr><td colSpan={8} className="p-4 text-zinc-500">No tickets visible to your role.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
