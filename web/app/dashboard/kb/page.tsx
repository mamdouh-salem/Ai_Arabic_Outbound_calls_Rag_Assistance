export default function KBPage() {
  return (
    <div className="p-8">
      <h1 className="text-2xl font-semibold mb-6">Knowledge Base</h1>
      <button className="bg-black text-white rounded px-4 py-2 mb-6">
        + Upload Document
      </button>
      <div className="bg-white dark:bg-zinc-900 rounded-lg shadow p-6 text-zinc-500">
        No documents uploaded yet.
      </div>
    </div>
  );
}