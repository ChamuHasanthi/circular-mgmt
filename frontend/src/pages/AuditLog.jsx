import { useEffect, useState } from "react";
import client from "../api/client";

// Administrator audit-log viewer — accountability / non-repudiation (NFR).
// Immutable trail of every recorded action, filterable by action and date.
const ACTION_TONE = (a) =>
  a.includes("FAILED") || a.includes("REJECTED") || a.includes("DELETED")
    ? "bg-red-50 text-status-unread"
    : a.includes("APPROVED") || a.includes("PUBLISHED") || a.includes("LOGIN")
    ? "bg-green-50 text-status-ack"
    : "bg-slate-100 text-ink";

export default function AuditLog() {
  const [rows, setRows] = useState([]);
  const [actions, setActions] = useState([]);
  const [action, setAction] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    const params = {};
    if (action) params.action = action;
    if (from) params.date_from = from;
    if (to) params.date_to = to;
    try {
      const { data } = await client.get("/audit", { params });
      setRows(data);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    client.get("/audit/actions").then((r) => setActions(r.data)).catch(() => {});
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="text-xs font-semibold uppercase tracking-wide text-brand-600">Security</div>
          <h1 className="text-xl font-bold text-ink">Audit Log</h1>
          <p className="mt-0.5 text-sm text-ink-muted">Immutable record of system activity.</p>
        </div>
        <form
          onSubmit={(e) => { e.preventDefault(); load(); }}
          className="flex flex-wrap items-center gap-2"
        >
          <select className="input" value={action} onChange={(e) => setAction(e.target.value)}>
            <option value="">All actions</option>
            {actions.map((a) => <option key={a} value={a}>{a}</option>)}
          </select>
          <input type="date" className="input" value={from} onChange={(e) => setFrom(e.target.value)} />
          <input type="date" className="input" value={to} onChange={(e) => setTo(e.target.value)} />
          <button type="submit" className="btn-primary">Filter</button>
        </form>
      </div>

      <div className="card table-wrap">
        <table className="w-full min-w-[640px] text-sm">
          <thead className="bg-ink-surface text-left text-xs uppercase tracking-wide text-ink-muted">
            <tr>
              <th className="px-4 py-3 font-medium">When</th>
              <th className="px-4 py-3 font-medium">User</th>
              <th className="px-4 py-3 font-medium">Action</th>
              <th className="px-4 py-3 font-medium">Entity</th>
              <th className="px-4 py-3 font-medium">Detail</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-ink-line">
            {loading ? (
              <tr><td colSpan={5} className="px-4 py-8 text-center text-ink-muted">Loading…</td></tr>
            ) : rows.length === 0 ? (
              <tr><td colSpan={5} className="px-4 py-8 text-center text-ink-muted">No activity found.</td></tr>
            ) : (
              rows.map((r) => (
                <tr key={r.id} className="hover:bg-ink-surface/60">
                  <td className="px-4 py-3 text-xs text-ink-muted">
                    {r.created_at ? new Date(r.created_at).toLocaleString() : ""}
                  </td>
                  <td className="px-4 py-3 text-ink">{r.actor || "—"}</td>
                  <td className="px-4 py-3">
                    <span className={`badge ${ACTION_TONE(r.action)}`}>{r.action}</span>
                  </td>
                  <td className="px-4 py-3 text-xs text-ink-muted">
                    {r.entity_type}{r.entity_id ? ` #${r.entity_id}` : ""}
                  </td>
                  <td className="px-4 py-3 text-ink-muted">{r.detail || "—"}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
