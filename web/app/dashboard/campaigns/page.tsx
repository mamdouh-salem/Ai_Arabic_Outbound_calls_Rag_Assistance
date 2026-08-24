"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "../../apiClient";

type Ticket = {
  id: string;
  title: string;
  status: string;
  created_at: string;
};

export default function CampaignsPage() {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    async function fetchTickets() {
      try {
        const data = await apiFetch("/tickets");
        setTickets(data || []);
      } catch (err: any) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }
    fetchTickets();
  }, []);

  return (
    <div className="p-8">
      <h1 className="text-2xl font-semibold mb-6">Campaigns</h1>
      {loading && <p className="text-zinc-500">Loading...</p>}
      {error && <p className="text-red-600 text-sm">{error}</p>}
      <div className="bg-white dark:bg-zinc-900 rounded-lg shadow overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-zinc-50 dark:bg-zinc-800 text-left text-zinc-500">
            <tr>
              <th className="p-3">Title</th>
              <th className="p-3">Status</th>
              <th className="p-3">Created</th>
            </tr>
          </thead>
          <tbody>
            {!loading && tickets.length === 0 && !error && (
              <tr>
                <td colSpan={3} className="p-6 text-center text-zinc-400">
                  No tickets yet.
                </td>
              </tr>
            )}
            {tickets.map((t) => (
              <tr key={t.id} className="border-t border-zinc-100 dark:border-zinc-800">
                <td className="p-3">{t.title}</td>
                <td className="p-3">{t.status}</td>
                <td className="p-3">{new Date(t.created_at).toLocaleDateString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}