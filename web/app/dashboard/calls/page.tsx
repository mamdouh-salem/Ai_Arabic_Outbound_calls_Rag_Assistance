export default function CallsPage() {
  return (
    <div className="p-8">
      <h1 className="text-2xl font-semibold mb-6">Live Calls</h1>
      <div className="bg-white rounded-lg shadow overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-zinc-50 text-left text-zinc-500">
            <tr>
              <th className="p-3">Customer</th>
              <th className="p-3">Status</th>
              <th className="p-3">Duration</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td colSpan={3} className="p-6 text-center text-zinc-400">
                No active calls.
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}