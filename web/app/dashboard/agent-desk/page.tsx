"use client";

import { useEffect, useRef, useState } from "react";
import { chat, chatVoice } from "../../lib/console";

type Citation = { index: number; source: string; score: number; snippet: string };

export default function AgentDeskPage() {
  const [log, setLog] = useState("Ask a question about the knowledge base…");
  const [question, setQuestion] = useState("");
  const [persona, setPersona] = useState("default");
  const [language, setLanguage] = useState("arabic");
  const [category, setCategory] = useState("");
  const [recording, setRecording] = useState(false);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const logRef = useRef<HTMLDivElement>(null);
  const mediaRef = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const audioRef = useRef<HTMLAudioElement>(null);

  function scroll() {
    setTimeout(() => logRef.current?.scrollTo(0, logRef.current.scrollHeight), 50);
  }
  function write(s: string) { setLog((p) => p + s); scroll(); }

  async function ask(q: string, cat: string, per: string, lang: string) {
    write(`\n\n🧑 You: ${q}\n⏳ thinking…`);
    try {
      const res: any = await chat({
        question: q, ...(cat ? { category: cat } : {}), persona: per,
        ...(lang && lang !== "arabic" ? { language: lang } : {}),
      });
      const cites = (res.citations ?? [])
        .map((c: Citation) => `[${c.index}] ${c.source} (${c.score})`).join("\n");
      write(`\n\n🤖 Assistant [${res.persona}${res.language !== "arabic" ? " · " + res.language : ""}]:\n${res.answer}` +
        (res.citations?.length ? `\n\n📚 Citations:\n${cites}` : "\n\n(no KB sources matched)") +
        `\n— scope: ${res.workspace_scope} · chunks: ${res.chunks_used}`);
    } catch (e: any) {
      write(`\n❌ ${e.message}`);
    }
    scroll();
  }

  function handleAsk() {
    const q = question.trim();
    if (!q) return;
    setQuestion("");
    ask(q, category, persona, language);
  }

  async function toggleMic() {
    if (mediaRef.current && mediaRef.current.state === "recording") {
      mediaRef.current.stop();
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      chunks.current = [];
      const mr = new MediaRecorder(stream);
      mediaRef.current = mr;
      mr.ondataavailable = (e) => chunks.current.push(e.data);
      mr.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        setRecording(false);
        const blob = new Blob(chunks.current, { type: mr.mimeType || "audio/webm" });
        const fd = new FormData();
        fd.append("file", blob, "question.webm");
        if (category) fd.append("category", category);
        fd.append("persona", persona);
        if (language !== "arabic") fd.append("language", language);
        write(`\n\n🧑 [voice] ⏳ transcribing + thinking…`);
        try {
          const res: any = await chatVoice(fd);
          write(`\n\n🧑 [voice] ${res.question}\n\n🤖 Assistant:\n${res.answer}` +
            (res.citations?.length ? `\n\n📚 Citations:\n${res.citations.map((c: Citation) => `[${c.index}] ${c.source}`).join("\n")}` : ""));
          if (res.audio_url) {
            setAudioUrl(`http://localhost:8000${res.audio_url}`);
            setTimeout(() => audioRef.current?.play().catch(() => {}), 100);
          }
        } catch (e: any) { write(`\n❌ ${e.message}`); }
        scroll();
      };
      mr.start();
      setRecording(true);
    } catch { alert("Microphone permission denied"); }
  }

  return (
    <div className="p-8 space-y-4">
      <h1 className="text-2xl font-semibold">RAG Assistant</h1>
      <p className="text-sm text-zinc-600">
        Grounded answers from your workspace knowledge base, with citations.
      </p>

      <div className="grid md:grid-cols-2 gap-4">
        <div className="bg-white border border-zinc-200 rounded-xl p-4">
          <div ref={logRef}
            className="text-xs bg-zinc-950 text-zinc-100 border border-zinc-800 rounded-lg p-3 overflow-auto whitespace-pre-wrap"
            style={{ minHeight: 320, maxHeight: 480 }}>
            {log}
          </div>
          {audioUrl && (
            <audio ref={audioRef} src={audioUrl} controls className="w-full mt-3" />
          )}
        </div>
        <div className="bg-white border border-zinc-200 rounded-xl p-4 space-y-3">
          <div>
            <label className="text-xs text-zinc-500">Persona</label>
            <select value={persona} onChange={(e) => setPersona(e.target.value)}
              className="w-full border border-zinc-300 rounded-lg px-3 py-2 text-sm">
              <option value="default">default — professional MSA</option>
              <option value="egyptian_friendly">Egyptian friendly 🇪🇬</option>
              <option value="formal">formal — فصحى رسمية</option>
              <option value="concise">concise — مختصر جدًا</option>
              <option value="empathetic">empathetic — متعاطف</option>
              <option value="technical">technical — دقة تقنية</option>
            </select>
          </div>
          <div>
            <label className="text-xs text-zinc-500">Answer language</label>
            <select value={language} onChange={(e) => setLanguage(e.target.value)}
              className="w-full border border-zinc-300 rounded-lg px-3 py-2 text-sm">
              <option value="arabic">العربية</option><option value="english">English</option>
              <option value="spanish">Español</option><option value="german">Deutsch</option>
              <option value="french">Français</option>
            </select>
          </div>
          <div>
            <label className="text-xs text-zinc-500">Category filter (optional)</label>
            <select value={category} onChange={(e) => setCategory(e.target.value)}
              className="w-full border border-zinc-300 rounded-lg px-3 py-2 text-sm">
              <option value="">all categories</option>
              <option>routers</option><option>billing</option><option>accounts</option>
            </select>
          </div>
          <textarea value={question} onChange={(e) => setQuestion(e.target.value)} rows={3} dir="rtl"
            placeholder="اكتب سؤالك هنا…"
            className="w-full border border-zinc-300 rounded-lg px-3 py-2 text-sm" />
          <div className="flex gap-2">
            <button onClick={handleAsk}
              className="flex-1 bg-black text-white px-4 py-2 rounded-lg text-sm hover:bg-zinc-800">
              Ask 🤖
            </button>
            <button onClick={toggleMic}
              className={`flex-1 px-4 py-2 rounded-lg text-sm border ${
                recording ? "bg-red-600 border-red-500 text-white animate-pulse"
                          : "bg-white border-zinc-300 hover:bg-zinc-100"}`}>
              {recording ? "⏺ Recording… (click to send)" : "🎤 Ask by voice"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
