"use client";

import { useEffect, useState } from "react";
import { supabase } from "../../supabaseClient";

type Customer = {
  id: string;
  name: string;
  phone: string;
  created_at: string;
};

export default function CampaignsPage() {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    async function fetchCustomers() {
      const { data, error } = await supabase
        .from("customers")
        .select("id, name, phone, created_at")
        .order("created_at", { ascending: false });

      if (error) {
        setError(error.message);
      } else {
        setCustomers(data || []);
      }
      setLoading(false);
    }
    fetchCustomers();
  }, []);

  return (
    <div className="p-8">
      <h1 className="text-2xl font-semibold mb-6">Customers (test data)</h1>
      {loading && <p className="text-zinc-500">Loading...</p>}
      {error && <p className="text-red-600 text-sm">{error}</p>}
      {!loading && !error && customers.length === 0 && (
        <div className="bg-white dark:bg-zinc-900 rounded-lg shadow p-6 text-zinc-500">
          No customers yet.
        </div>
      )}
      {customers.length > 0 && (
        <div className="bg-white dark:bg-zinc-900 rounded-lg shadow overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-zinc-50 dark:bg-zinc-800 text-left text-zinc-500">
              <tr>
                <th className="p-3">Name</th>
                <th className="p-3">Phone</th>
                <th className="p-3">Created</th>
              </tr>
            </thead>
            <tbody>
              {customers.map((c) => (
                <tr key={c.id} className="border-t border-zinc-100 dark:border-zinc-800">
                  <td className="p-3">{c.name}</td>
                  <td className="p-3">{c.phone}</td>
                  <td className="p-3">{new Date(c.created_at).toLocaleDateString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}