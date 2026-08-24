"use client";

import { useEffect, useState } from "react";
import { supabase } from "../../supabaseClient";

type Member = {
  id: string;
  role: string;
  created_at: string;
  users: { email: string } | null;
};

export default function WorkspacePage() {
  const [members, setMembers] = useState<Member[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    async function fetchMembers() {
      const { data, error } = await supabase
        .from("workspace_members")
        .select("id, role, created_at, users!workspace_members_user_id_fkey(email)")
        .order("created_at", { ascending: false });

      if (error) {
        setError(error.message);
      } else {
        setMembers((data as unknown as Member[]) || []);
      }
      setLoading(false);
    }
    fetchMembers();
  }, []);

  return (
    <div className="p-8">
      <h1 className="text-2xl font-semibold mb-6">Workspace</h1>
      {loading && <p className="text-zinc-500">Loading...</p>}
      {error && <p className="text-red-600 text-sm">{error}</p>}
      <div className="bg-white dark:bg-zinc-900 rounded-lg shadow overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-zinc-50 dark:bg-zinc-800 text-left text-zinc-500">
            <tr>
              <th className="p-3">Email</th>
              <th className="p-3">Role</th>
            </tr>
          </thead>
          <tbody>
            {!loading && members.length === 0 && (
              <tr>
                <td colSpan={2} className="p-6 text-center text-zinc-400">
                  No members yet.
                </td>
              </tr>
            )}
            {members.map((m) => (
              <tr key={m.id} className="border-t border-zinc-100 dark:border-zinc-800">
                <td className="p-3">{m.users?.email ?? "—"}</td>
                <td className="p-3">{m.role}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}