"use client";

import { createContext, useContext, useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { supabase } from "../supabaseClient";
import {
  getIdentity,
  setCachedIdentity,
  setWorkspaceScope,
  type Identity,
} from "../lib/console";

const IdentityContext = createContext<Identity | null>(null);
export function useIdentity() {
  return useContext(IdentityContext);
}

const TABS = [
  { href: "/dashboard", label: "Dashboard", roles: ["agent", "admin", "super_admin"] },
  { href: "/dashboard/agent-desk", label: "RAG Chat", roles: ["agent", "admin", "super_admin"] },
  { href: "/dashboard/tickets", label: "Tickets", roles: ["agent", "admin", "super_admin"] },
  { href: "/dashboard/calls", label: "Calls", roles: ["agent", "admin", "super_admin"] },
  { href: "/dashboard/kb", label: "Knowledge Base", roles: ["admin", "super_admin"] },
  { href: "/dashboard/data-insights", label: "Data Insights", roles: ["admin", "super_admin"] },
  { href: "/dashboard/workspace", label: "Users & Workspaces", roles: ["admin", "super_admin"] },
  { href: "/dashboard/campaigns", label: "Call Center", roles: ["admin", "super_admin"] },
];

const ROLE_STYLE: Record<string, string> = {
  super_admin: "bg-purple-100 text-purple-700 border-purple-200",
  admin: "bg-amber-100 text-amber-700 border-amber-200",
  agent: "bg-green-100 text-green-700 border-green-200",
};

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [ready, setReady] = useState(false);
  const [wsInput, setWsInput] = useState("");
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    (async () => {
      const { data } = await supabase.auth.getUser();
      if (!data.user) {
        router.push("/login");
        return;
      }
      try {
        const id = await getIdentity();
        setIdentity(id);
        setCachedIdentity(id);
        setReady(true);
      } catch {
        router.push("/login");
      }
    })();
  }, [router]);

  async function handleLogout() {
    await supabase.auth.signOut();
    router.push("/login");
  }

  function applyWorkspace() {
    setWorkspaceScope(wsInput.trim());
    window.location.reload();
  }

  const role = identity?.role ?? "agent";

  return (
    <IdentityContext.Provider value={identity}>
      <div className="min-h-screen flex bg-zinc-50">
        {/* sidebar — Teammate B's original design */}
        <nav className="w-56 shrink-0 bg-white border-r border-zinc-200 p-4 flex flex-col">
          <h2 className="font-semibold text-lg mb-4 px-2 text-black">Outbound AI</h2>
          <div className="flex flex-col gap-1 flex-1">
            {TABS.filter((t) => t.roles.includes(role)).map((t) => (
              <Link
                key={t.href}
                href={t.href}
                className={`px-2 py-2 rounded text-sm ${
                  pathname === t.href
                    ? "bg-zinc-100 text-black font-medium"
                    : "text-zinc-700 hover:bg-zinc-100"
                }`}
              >
                {t.label}
              </Link>
            ))}
          </div>

          {/* super-admin workspace scope */}
          {role === "super_admin" && (
            <div className="mb-3 border-t border-zinc-200 pt-3">
              <p className="text-[11px] text-zinc-500 mb-1 px-2">
                Workspace scope (super admin)
              </p>
              <input
                value={wsInput}
                onChange={(e) => setWsInput(e.target.value)}
                placeholder="empty = all"
                className="w-full border border-zinc-300 rounded px-2 py-1 text-xs mb-1"
              />
              <button
                onClick={applyWorkspace}
                className="w-full bg-zinc-900 text-white rounded py-1 text-xs hover:bg-zinc-700"
              >
                Apply
              </button>
            </div>
          )}

          <div className="border-t border-zinc-200 pt-3 text-xs text-zinc-600 break-all px-2">
            {identity?.email}
          </div>
          <span
            className={`mt-2 mx-2 text-center text-[11px] border rounded-full px-2 py-0.5 ${
              ROLE_STYLE[role] ?? ""
            }`}
          >
            {role}
          </span>
          <button
            onClick={handleLogout}
            className="mt-2 mx-2 text-xs text-zinc-600 underline hover:text-black text-left"
          >
            Log out
          </button>
        </nav>

        {/* content */}
        <div className="flex-1 overflow-x-auto">
          {ready ? children : <p className="p-8 text-zinc-500">Loading…</p>}
        </div>
      </div>
    </IdentityContext.Provider>
  );
}
