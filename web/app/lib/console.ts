"use client";
import { supabase } from "../supabaseClient";

export const API_BASE = "http://localhost:8000";

let workspaceScope = "";
if (typeof window !== "undefined") {
  workspaceScope = localStorage.getItem("obai_ws") ?? "";
}
export function setWorkspaceScope(v: string) {
  workspaceScope = v;
  if (typeof window !== "undefined") localStorage.setItem("obai_ws", v);
}
export function getWorkspaceScope() {
  return workspaceScope;
}

export type Identity = {
  user_id: string;
  workspace_id: string | null;
  role: "agent" | "admin" | "super_admin";
  email: string;
};

export async function apiFetch(path: string, options: RequestInit = {}) {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string> | undefined),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (typeof window !== "undefined") {
    const ws = localStorage.getItem("obai_ws");
    if (ws && identityCache?.role === "super_admin")
      headers["X-Workspace-Id"] = ws;
  }
  if (!(options.body instanceof FormData) && options.body) {
    headers["Content-Type"] = "application/json";
  }
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (res.status === 401 && typeof window !== "undefined") {
    await supabase.auth.signOut();
    window.location.href = "/login";
    throw new Error("Session expired");
  }
  if (!res.ok) {
    const text = await res.text();
    let detail = text;
    try {
      const j = JSON.parse(text);
      detail = j.detail ?? text;
    } catch {}
    throw new Error(detail || `API error ${res.status}`);
  }
  const text = await res.text();
  return text ? JSON.parse(text) : null;
}

let identityCache: Identity | null = null;
export function getCachedIdentity() {
  return identityCache;
}
export function setCachedIdentity(i: Identity | null) {
  identityCache = i;
}

export async function getIdentity(): Promise<Identity> {
  const id = (await apiFetch("/health/auth")) as Identity;
  identityCache = id;
  return id;
}

/* ---------------- data endpoints ---------------- */
export const getTickets = () => apiFetch("/tickets");
export const getCalls = () => apiFetch("/calls");
export const getKbDocs = () => apiFetch("/kb/documents");
export const uploadKb = (fd: FormData) =>
  apiFetch("/kb/documents", { method: "POST", body: fd });
export const deleteKbDoc = (source: string) =>
  apiFetch(`/kb/documents/${encodeURIComponent(source)}`, { method: "DELETE" });

export function chat(body: {
  question: string;
  category?: string;
  persona?: string;
  language?: string;
}) {
  return apiFetch("/kb/chat", { method: "POST", body: JSON.stringify(body) });
}
export function chatVoice(fd: FormData) {
  return apiFetch("/kb/chat/voice", { method: "POST", body: fd });
}
export function dataQuery(question: string) {
  return apiFetch("/data/query", {
    method: "POST",
    body: JSON.stringify({ question }),
  });
}

/* ---------------- admin endpoints ---------------- */
export const listUsers = () => apiFetch("/admin/users");
export function createUser(body: {
  email: string;
  display_name: string;
  role: string;
  workspace_id?: string;
  password?: string;
}) {
  return apiFetch("/admin/users", { method: "POST", body: JSON.stringify(body) });
}
export const setPlatformRole = (userId: string, role: string) =>
  apiFetch(`/admin/users/${userId}/platform-role?new_role=${role}`, {
    method: "PATCH",
  });
export function resetUserPassword(userId: string, newPassword?: string) {
  return apiFetch(`/admin/users/${userId}/password`, {
    method: "PATCH",
    body: JSON.stringify({ ...(newPassword ? { new_password: newPassword } : {}) }),
  });
}
export const listWorkspaces = () => apiFetch("/admin/workspaces");
export function createWorkspace(body: {
  name: string;
  slug: string;
  plan: string;
}) {
  return apiFetch("/admin/workspaces", {
    method: "POST",
    body: JSON.stringify(body),
  });
}
export const getHierarchy = () =>
  apiFetch("/admin/workspaces/hierarchy/tree");

/* ---------------- calls ---------------- */
export function startCall(body: {
  phone: string;
  ticket_id?: string;
  ticket_title?: string;
  category?: string;
  customer_name?: string;
}) {
  return apiFetch("/start-call", { method: "POST", body: JSON.stringify(body) });
}
export const callTicket = (ticketId: string) =>
  apiFetch(`/tickets/${ticketId}/call`, { method: "POST" });
