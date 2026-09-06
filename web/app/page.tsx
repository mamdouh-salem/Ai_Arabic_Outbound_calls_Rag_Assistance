"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function Home() {
  const router = useRouter();
  useEffect(() => {
    router.push("/dashboard");
  }, [router]);
  return (
    <div className="min-h-screen flex items-center justify-center text-zinc-500">
      Redirecting…
    </div>
  );
}
