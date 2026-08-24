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
  super_admin: "bg-purple-500/20 text-purple-300 border-purple-500/50",
  admin: "bg-amber-500/20 text-amber-300 border-amber-500/50",
  agent: "bg-green-500/20 text-green-300 border-green-500/50",
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
      <div className="min-h-screen bg-zinc-950 text-zinc-100">
        {/* topbar */}
        <header className="sticky top-0 z-20 flex items-center gap-4 border-b border-zinc-800 bg-zinc-900 px-5 h-14">
          <span className="font-semibold">🎙️ Outbound AI</span>
          <nav className="flex flex-1 gap-1 overflow-x-auto">
            {TABS.filter((t) => t.roles.includes(role)).map((t) => (
              <Link
                key={t.href}
                href={t.href}
                className={`px-3 py-1.5 rounded-lg text-sm whitespace-nowrap ${
                  pathname === t.href
                    ? "bg-zinc-800 text-white"
                    : "text-zinc-400 hover:text-zinc-100"
                }`}
              >
                {t.label}
              </Link>
            ))}
          </nav>
          <span className="text-sm text-zinc-400 hidden md:inline">
            {identity?.email}
          </span>
          <span
            className={`px-2.5 py-0.5 rounded-full text-xs border ${
              ROLE_STYLE[role] ?? ""
            }`}
          >
            {role}
          </span>
          <button
            onClick={handleLogout}
            className="text-sm text-zinc-400 hover:text-white border border-zinc-700 rounded-lg px-3 py-1"
          >
            Logout
          </button>
        </header>

        {/* super-admin workspace scope bar */}
        {role === "super_admin" && (
          <div className="flex items-center gap-3 px-5 py-2 bg-purple-950/40 border-b border-zinc-800 text-xs">
            <span className="text-purple-300">
              Workspace scope (super admin):
            </span>
            <input
              value={wsInput}
              onChange={(e) => setWsInput(e.target.value)}
              placeholder="leave empty = all workspaces"
              className="bg-zinc-900 border border-zinc-700 rounded-lg px-2 py-1 w-72"
            />
            <button
              onClick={applyWorkspace}
              className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-1 hover:bg-zinc-700"
            >
              Apply
            </button>
          </div>
        )}

        <main className="max-w-6xl mx-auto p-6">
          {ready ? children : <p className="text-zinc-500">Loading…</p>}
        </main>
      </div>
    </IdentityContext.Provider>
  );
}
