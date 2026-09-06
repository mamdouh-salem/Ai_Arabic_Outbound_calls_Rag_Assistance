"use client";

import { useState } from "react";
import { supabase } from "../supabaseClient";

export default function SignupPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setMessage("");
    const { data, error } = await supabase.auth.signUp({
      email,
      password,
    });
    if (error) {
      setMessage(`Error: ${error.message}`);
    } else {
      setMessage("Account created! Check your email to confirm, or try logging in.");
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-50">
      <form onSubmit={handleSubmit} className="flex flex-col gap-4 w-80 p-8 bg-white rounded-lg shadow">
        <h1 className="text-2xl font-semibold text-center">Sign Up</h1>
        <input
          type="email"
          placeholder="Email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="border rounded px-3 py-2"
        />
        <input
          type="password"
          placeholder="Password (min 6 characters)"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="border rounded px-3 py-2"
        />
        {message && <p className="text-sm text-zinc-700">{message}</p>}
        <button type="submit" className="bg-black text-white rounded py-2">Sign Up</button>
      </form>
    </div>
  );
}