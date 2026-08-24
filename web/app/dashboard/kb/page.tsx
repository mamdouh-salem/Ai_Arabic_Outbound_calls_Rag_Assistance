"use client";

import { useEffect, useRef, useState } from "react";
import { deleteKbDoc, getKbDocs, uploadKb } from "../../lib/console";

type Doc = { source: string; chunks: number; category?: string };

export default function KbPage() {
  const [docs, setDocs] = useState<Doc[]>([]);
  const [category, setCategory] = useState("");
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  async function load() {
    setDocs((await getKbDocs()) as Doc[]);
  }
  useEffect(() => { load(); }, []);

  async function upload() {
    if (!category.trim()) return setMsg("Category is required");
    const fd = new FormData();
    fd.append("category", category.trim());
    if (title.trim()) fd.append("title", title.trim());
    if (fileRef.current?.files?.length) fd.append("file", fileRef.current.files[0]);
    else if (content.trim()) fd.append("content", content);
    else return setMsg("Attach a file or paste content");
    setBusy(true);
    try {
      const res: any = await uploadKb(fd);
      setMsg(`✅ Ingested "${res.source}" — ${res.chunks} chunk(s)`);
      setContent("");
      if (fileRef.current) fileRef.current.value = "";
      load();
    } catch (e: any) { setMsg("❌ " + e.message); }
    finally { setBusy(false); }
  }

  async function remove(source: string) {
    if (!confirm(`Delete every chunk of "${source}"?`)) return;
    try { await deleteKbDoc(source); load(); } catch (e: any) { alert(e.message); }
  }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Knowledge Base</h1>
      <div className="grid md:grid-cols-2 gap-4">
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 space-y-3">
          <h3 className="font-semibold">Upload document</h3>
          <input value={category} onChange={(e) => setCategory(e.target.value)}
            placeholder="category * (billing / routers / accounts …)"
            className="w-full bg-zinc-950 border border-zinc-800 rounded-lg px-3 py-2 text-sm" />
          <input value={title} onChange={(e) => setTitle(e.target.value)}
            placeholder="title (defaults to filename)"
            className="w-full bg-zinc-950 border border-zinc-800 rounded-lg px-3 py-2 text-sm" />
          <input ref={fileRef} type="file" accept=".txt,.md,.markdown,.pdf,.docx,.csv,.json"
            className="w-full text-sm" />
          <textarea value={content} onChange={(e) => setContent(e.target.value)} rows={6} dir="rtl"
            placeholder="…أو الصق النص العربي هنا"
            className="w-full bg-zinc-950 border border-zinc-800 rounded-lg px-3 py-2 text-sm" />
          <button onClick={upload} disabled={busy}
            className="bg-sky-600 hover:bg-sky-500 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm">
            {busy ? "Ingesting…" : "⬆ Upload & Ingest"}
          </button>
          {msg && <p className="text-xs text-zinc-300">{msg}</p>}
        </div>
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
          <h3 className="font-semibold mb-3">Documents in workspace</h3>
          <table className="w-full text-sm">
            <tbody>
              {docs.map((d) => (
                <tr key={d.source} className="border-b border-zinc-800/60">
                  <td className="p-2" dir="rtl">{d.source}</td>
                  <td className="p-2">{d.chunks}</td>
                  <td className="p-2">{d.category ?? "—"}</td>
                  <td className="p-2">
                    <button onClick={() => remove(d.source)}
                      className="bg-red-600/80 hover:bg-red-500 text-white text-xs px-2.5 py-1 rounded">
                      delete
                    </button>
                  </td>
                </tr>
              ))}
              {!docs.length && <tr><td className="p-2 text-zinc-500">No documents yet.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
