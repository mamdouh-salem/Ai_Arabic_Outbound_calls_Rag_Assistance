import Link from "next/link";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const links = [
    { href: "/dashboard", label: "Home" },
    { href: "/dashboard/campaigns", label: "Campaigns" },
    { href: "/dashboard/calls", label: "Live Calls" },
    { href: "/dashboard/agent-desk", label: "Agent Desk" },
    { href: "/dashboard/kb", label: "Knowledge Base" },
    { href: "/dashboard/reports", label: "Reports" },
    { href: "/dashboard/workspace", label: "Workspace" },
  ];

  return (
    <div className="min-h-screen flex">
      <nav className="w-56 bg-white border-r p-4 flex flex-col gap-1">
        <h2 className="font-semibold text-lg mb-4 px-2">Outbound AI</h2>
        {links.map((link) => (
          <Link
            key={link.href}
            href={link.href}
            className="px-2 py-2 rounded hover:bg-zinc-100 text-sm text-zinc-700"
          >
            {link.label}
          </Link>
        ))}
      </nav>
      <div className="flex-1">{children}</div>
    </div>
  );
}