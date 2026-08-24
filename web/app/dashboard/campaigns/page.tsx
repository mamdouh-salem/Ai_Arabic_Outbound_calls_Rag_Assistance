export default function CampaignsPage() {
  return (
    <div className="p-8">
      <h1 className="text-2xl font-semibold mb-6">Campaigns</h1>
      <button className="bg-black text-white rounded px-4 py-2 mb-6">
        + New Campaign
      </button>
      <div className="bg-white rounded-lg shadow p-6 text-zinc-500">
        No campaigns yet.
      </div>
    </div>
  );
}