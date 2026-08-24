"use client";

import { useEffect, useState } from "react";
import { useIdentity } from "../layout";
import {
  createUser, getHierarchy, listUsers, listWorkspaces,
  createWorkspace, setPlatformRole,
} from "../../lib/console";

export default function WorkspacePage() {
  const me = useIdentity();
  const isSuper = me?.role === "super_admin";

  const [users, setUsers] = useState<any[]>([]);
  const [workspaces, setWorkspaces] = useState<any[]>([]);
  const [tree, setTree] = useState<any[]>([]);
  const [msg, setMsg] = useState("");

  // create-user form
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState("agent");
  const [wsId, setWsId] = useState("");
  const [password, setPassword] = useState("");
  const [created, setCreated] = useState<any>(null);

  // workspace form
  const [wName, setWName] = useState("");
  const [wSlug, setWSlug] = useState("");
  const [wPlan, setWPlan] = useState("free");

  async function load() {
    try { setUsers((await listUsers()) as any[]); } catch {}
    if (isSuper) {
      try { setWorkspaces((await listWorkspaces()) as any[]); } catch {}
      try { setTree((await getHierarchy()) as any[]); } catch {}
    }
  }
  useEffect(() => { if (me) load(); }, [me]);

  async function handleCreate() {
    if (!email.trim() || !name.trim()) return setMsg("Email and name required");
    try {
      const res: any = await createUser({
        email: email.trim(), display_name: name.trim(), role,
        ...(role !== "super_admin" ? {} : {}),
        ...(wsId.trim() && role !== "agent" ? { workspace_id: wsId.trim() } : {}),
        ...(password ? { password } : {}),
      });
      setCreated(res);
      if (res.generated_password)
        setMsg(`✅ Created — generated password (shown ONCE): ${res.generated_password}`);
      else setMsg("✅ User created");
      setEmail(""); setName(""); setPassword("");
      load();
    } catch (e: any) { setMsg("❌ " + e.message); }
  }

  async function promote(id: string) {
    try { await setPlatformRole(id, "admin"); load(); } catch (e: any) { alert(e.message); }
  }

  async function handleCreateWs() {
    if (!wName.trim() || !wSlug.trim()) return setMsg("Name and slug required");
    try {
      await createWorkspace({ name: wName.trim(), slug: wSlug.trim().toLowerCase(), plan: wPlan });
      setMsg(`✅ Workspace "${wName}" created`); setWName(""); setWSlug(""); load();
    } catch (e: any) { setMsg("❌ " + e.message); }
  }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Users & Workspaces</h1>
      {msg && <p className="text-sm text-zinc-300">{msg}</p>}

      <div className="grid md:grid-cols-2 gap-4">
        {/* create user */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 space-y-3">
          <h3 className="font-semibold">Create user</h3>
          <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="email"
            className="w-full bg-zinc-950 border border-zinc-800 rounded-lg px-3 py-2 text-sm" />
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="display name"
            className="w-full bg-zinc-950 border border-zinc-800 rounded-lg px-3 py-2 text-sm" />
          <select value={role} onChange={(e) => setRole(e.target.value)}
            className="w-full bg-zinc-950 border border-zinc-800 rounded-lg px-3 py-2 text-sm"
            disabled={me?.role === "admin"}>
            <option value="agent">agent</option>
            {isSuper && <option value="admin">admin</option>}
            {isSuper && <option value="super_admin">super_admin</option>}
          </select>
          {isSuper && role !== "super_admin" && (
            <input value={wsId} onChange={(e) => setWsId(e.target.value)}
              placeholder="workspace id (required for admin/agent)"
              className="w-full bg-zinc-950 border border-zinc-800 rounded-lg px-3 py-2 text-sm" />
          )}
          <input value={password} onChange={(e) => setPassword(e.target.value)}
            type="text" placeholder="password (empty = auto-generate)"
            className="w-full bg-zinc-950 border border-zinc-800 rounded-lg px-3 py-2 text-sm" />
          <button onClick={handleCreate}
            className="bg-sky-600 hover:bg-sky-500 text-white px-4 py-2 rounded-lg text-sm">
            Create account
          </button>
          {created?.generated_password && (
            <p className="text-amber-400 text-xs break-all">
              ⚠️ Generated password (ONCE): {created.generated_password}
            </p>
          )}
        </div>

        {/* users list */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
          <h3 className="font-semibold mb-3">Users visible to you</h3>
          <table className="w-full text-sm">
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className="border-b border-zinc-800/60">
                  <td className="p-2">{u.email}</td>
                  <td className="p-2">{u.display_name ?? "—"}</td>
                  <td className="p-2">
                    <span className="text-xs border border-zinc-700 rounded px-1.5 py-0.5">
                      {u.platform_role}
                    </span>
                  </td>
                  {isSuper && u.platform_role !== "admin" && (
                    <td className="p-2">
                      <button onClick={() => promote(u.id)}
                        className="text-xs border border-zinc-700 rounded px-2 py-1 hover:bg-zinc-800">
                        promote
                      </button>
                    </td>
                  )}
                </tr>
              ))}
              {!users.length && <tr><td className="p-2 text-zinc-500">No users visible.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      {isSuper && (
        <>
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
            <h3 className="font-semibold mb-3">Platform hierarchy</h3>
            <pre className="text-xs bg-zinc-950 border border-zinc-800 rounded-lg p-3 overflow-auto max-h-72">
{tree.map((w) => {
  let s = `🏢 ${w.workspace.name} (${w.workspace.slug}, ${w.workspace.plan})\n`;
  if (!w.admins.length && !w.agents.length) s += "   └─ (no members)\n";
  w.admins.forEach((a: any) => { s += `   ├─ 👔 ADMIN ${a.name ?? "?"} <${a.email}>\n`; });
  w.agents.forEach((a: any) => { s += `   ├─ 🙋 agent  ${a.name ?? "?"} <${a.email}>\n`; });
  return s;
}).join("\n")}
            </pre>
          </div>

          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
            <h3 className="font-semibold mb-3">Workspaces</h3>
            <table className="w-full text-sm mb-4">
              <tbody>
                {workspaces.map((w) => (
                  <tr key={w.id} className="border-b border-zinc-800/60">
                    <td className="p-2">{w.name}</td>
                    <td className="p-2"><code className="text-xs">{w.slug}</code></td>
                    <td className="p-2">{w.plan}</td>
                    <td className="p-2">{w.members ?? 0} members ({w.admins ?? 0} admin)</td>
                    <td className="p-2 font-mono text-xs text-zinc-500">{w.id.slice(0, 13)}…</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="grid md:grid-cols-3 gap-3 items-end">
              <input value={wName} onChange={(e) => setWName(e.target.value)} placeholder="workspace name"
                className="bg-zinc-950 border border-zinc-800 rounded-lg px-3 py-2 text-sm" />
              <input value={wSlug} onChange={(e) => setWSlug(e.target.value)} placeholder="slug (acme-telecom)"
                className="bg-zinc-950 border border-zinc-800 rounded-lg px-3 py-2 text-sm" />
              <div className="flex gap-2">
                <select value={wPlan} onChange={(e) => setWPlan(e.target.value)}
                  className="bg-zinc-950 border border-zinc-800 rounded-lg px-3 py-2 text-sm flex-1">
                  <option>free</option><option>pro</option><option>enterprise</option>
                </select>
                <button onClick={handleCreateWs}
                  className="bg-sky-600 hover:bg-sky-500 text-white px-4 py-2 rounded-lg text-sm whitespace-nowrap">
                  Create
                </button>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
