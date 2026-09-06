"use client";

import { useEffect, useState } from "react";
import { useIdentity } from "./layout";
import { getCalls, getIdentity, getKbDocs, getTickets, listUsers } from "../lib/console";

export default function DashboardPage() {
  const me = useIdentity();
  const [cards, setCards] = useState<[string, number][]>([]);

  useEffect(() => {
    if (!me) return;
    (async () => {
      const out: [string, number][] = [];
      const safe = async (label: string, fn: () => Promise<unknown[]>) => {
        try { out.push([label, ((await fn()) as unknown[]).length]); } catch {}
      };
      await safe("Tickets visible to you", getTickets);
      await safe("Calls visible to you", getCalls);
      if (me.role !== "agent") await safe("KB documents", getKbDocs);
      if (me.role === "super_admin") await safe("Users on platform", listUsers);
      setCards(out);
    })();
  }, [me]);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Dashboard</h1>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {cards.map(([label, n]) => (
          <div key={label} className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
            <div className="text-3xl font-bold text-sky-400">{n}</div>
            <div className="text-xs text-zinc-500 mt-1">{label}</div>
          </div>
        ))}
      </div>

      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
        <h3 className="font-semibold mb-3">My identity</h3>
        <pre className="text-xs bg-zinc-950 border border-zinc-800 rounded-lg p-3 overflow-auto">
{JSON.stringify(me, null, 2)}
        </pre>
      </div>

      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
        <h3 className="font-semibold mb-2">Agentic workflow</h3>
        <p className="text-xs text-zinc-500 mb-3">
          The compiled LangGraph — served live by the API, no LangSmith login.
        </p>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src="http://localhost:8000/workflow.png"
          alt="workflow diagram"
          className="rounded-lg border border-zinc-800 bg-white max-w-full"
        />
      </div>
    </div>
  );
}
