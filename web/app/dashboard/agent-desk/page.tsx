"use client";

import { useState } from "react";

export default function AgentDeskPage() {
  const [message, setMessage] = useState("");

  return (
    <div className="p-8 flex flex-col h-screen">
      <h1 className="text-2xl font-semibold mb-6">Agent Desk</h1>
      <div className="flex-1 bg-white rounded-lg shadow p-4 mb-4 overflow-y-auto">
        <p className="text-zinc-400 text-sm">Ask the knowledge base a question...</p>
      </div>
      <div className="flex gap-2">
        <input
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="Type a question..."
          className="flex-1 border rounded px-3 py-2"
        />
        <button className="bg-black text-white rounded px-4 py-2">Send</button>
      </div>
    </div>
  );
}