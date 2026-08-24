export default function WorkspacePage() {
  return (
    <div className="p-8">
      <h1 className="text-2xl font-semibold mb-6">Workspace</h1>
      <button className="bg-black text-white rounded px-4 py-2 mb-6">
        + Invite Member
      </button>
      <div className="bg-white dark:bg-zinc-900 rounded-lg shadow overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-zinc-50 dark:bg-zinc-800 text-left text-zinc-500">
            <tr>
              <th className="p-3">Email</th>
              <th className="p-3">Role</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td colSpan={2} className="p-6 text-center text-zinc-400">
                No members yet.
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}