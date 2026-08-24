"use client";

import { useState } from "react";
import { apiFetch } from "../../apiClient";

type Message = { role: "user" | "assistant"; content: string };

export default function AgentDeskPage() {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleSend() {
    if (!input.trim()) return;
    const question = input;
    setMessages((prev) => [...prev, { role: "user", content: question }]);
    setInput("");
    setLoading(true);
    setError("");
    try {
      const data = await apiFetch("/kb/chat", {
        method: "POST",
        body: JSON.stringify({ question }),
      });
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.answer ?? JSON.stringify(data) },
      ]);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="p-8 flex flex-col h-screen">
      <h1 className="text-2xl font-semibold mb-6">Agent Desk</h1>
      <div className="flex-1 bg-white dark:bg-zinc-900 rounded-lg shadow p-4 mb-4 overflow-y-auto flex flex-col gap-3">
        {messages.length === 0 && (
          <p className="text-zinc-400 text-sm">Ask the knowledge base a question...</p>
        )}
        {messages.map((m, i) => (
          <div
            key={i}
            className={`max-w-[80%] p-3 rounded-lg text-sm ${
              m.role === "user"
                ? "self-end bg-black text-white"
                : "self-start bg-zinc-100 dark:bg-zinc-800 text-zinc-800 dark:text-zinc-200"
            }`}
          >
            {m.content}
          </div>
        ))}
        {loading && <p className="text-zinc-400 text-sm">Thinking...</p>}
        {error && <p className="text-red-600 text-sm">{error}</p>}
      </div>
      <div className="flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSend()}
          placeholder="Type a question..."
          className="flex-1 border rounded px-3 py-2"
        />
        <button onClick={handleSend} className="bg-black text-white rounded px-4 py-2">
          Send
        </button>
      </div>
    </div>
  );
}