export default function ReportsPage() {
  return (
    <div className="p-8">
      <h1 className="text-2xl font-semibold mb-6">Reports</h1>
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-white dark:bg-zinc-900 rounded-lg shadow p-6">
          <p className="text-zinc-500 text-sm">First Call Resolution</p>
          <p className="text-3xl font-semibold mt-2">—</p>
        </div>
        <div className="bg-white dark:bg-zinc-900 rounded-lg shadow p-6">
          <p className="text-zinc-500 text-sm">Total Calls</p>
          <p className="text-3xl font-semibold mt-2">—</p>
        </div>
        <div className="bg-white dark:bg-zinc-900 rounded-lg shadow p-6">
          <p className="text-zinc-500 text-sm">Escalation Rate</p>
          <p className="text-3xl font-semibold mt-2">—</p>
        </div>
      </div>
    </div>
  );
}