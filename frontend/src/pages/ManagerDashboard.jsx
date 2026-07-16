import { Fragment, useEffect, useState } from "react";
import client from "../api/client";
import BarChart from "../components/BarChart.jsx";
import Icon from "../components/Icon.jsx";

// WF-04 — Manager compliance dashboard (FR-31–35).
const TONE = {
  brand: "text-brand-600",
  ack: "text-status-ack",
  read: "text-status-read",
  unread: "text-status-unread",
};

export default function ManagerDashboard() {
  const [overview, setOverview] = useState(null);
  const [trends, setTrends] = useState(null);
  const [circulars, setCirculars] = useState([]);
  const [ai, setAi] = useState(null);
  const [userStats, setUserStats] = useState(null);
  const [expanded, setExpanded] = useState(null); // circular id
  const [employees, setEmployees] = useState([]);

  useEffect(() => {
    client.get("/dashboard/overview").then((r) => setOverview(r.data));
    client.get("/dashboard/trends").then((r) => setTrends(r.data));
    client.get("/dashboard/circulars").then((r) => setCirculars(r.data));
    client.get("/dashboard/ai-performance").then((r) => setAi(r.data));
    client.get("/dashboard/users").then((r) => setUserStats(r.data)).catch(() => {});
  }, []);

  async function toggle(id) {
    if (expanded === id) return setExpanded(null);
    const { data } = await client.get(`/dashboard/circulars/${id}/acknowledgements`);
    setEmployees(data);
    setExpanded(id);
  }

  async function exportReport(fmt) {
    const res = await client.get(`/dashboard/export.${fmt}`, { responseType: "blob" });
    const url = URL.createObjectURL(res.data);
    const a = document.createElement("a");
    a.href = url;
    a.download = `compliance_report.${fmt}`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const kpis = overview
    ? [
        { label: "Published", value: overview.published, tone: "brand", icon: "document", chip: "bg-brand-50 text-brand-600" },
        { label: "Acknowledged", value: overview.acknowledged, tone: "ack", icon: "check", chip: "bg-green-50 text-status-ack" },
        { label: "Pending", value: overview.pending, tone: "read", icon: "inbox", chip: "bg-amber-50 text-status-read" },
        { label: "Overdue", value: overview.overdue, tone: "unread", icon: "bell", chip: "bg-red-50 text-status-unread" },
      ]
    : [];

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-ink">Dashboard</h1>
        </div>
        <div className="flex gap-2">
          <button onClick={() => exportReport("csv")} className="btn-ghost">Export CSV</button>
          <button onClick={() => exportReport("pdf")} className="btn-primary">Export PDF</button>
        </div>
      </div>

      {/* KPI cards (FR-31) */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {kpis.map((k) => (
          <div key={k.label} className="card card-hover flex items-center gap-4 p-5">
            <div className={`grid h-12 w-12 place-items-center rounded-xl ${k.chip}`}>
              <Icon name={k.icon} className="h-5 w-5" />
            </div>
            <div>
              <div className="text-xs font-medium uppercase tracking-wide text-ink-muted">{k.label}</div>
              <div className={`text-2xl font-bold leading-tight ${TONE[k.tone]}`}>{k.value}</div>
            </div>
          </div>
        ))}
      </div>

      {overview && (
        <div className="card p-5">
          <div className="mb-1 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-ink">Overall acknowledgement rate</h2>
            <span className="text-sm font-bold text-brand-600">{overview.ack_rate}%</span>
          </div>
          <div className="h-3 overflow-hidden rounded-full bg-ink-surface">
            <div className="h-full bg-status-ack" style={{ width: `${overview.ack_rate}%` }} />
          </div>
        </div>
      )}

      {/* Charts (FR-33) */}
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="card p-6">
          <h2 className="mb-3 text-sm font-semibold text-ink">Category distribution</h2>
          <BarChart data={(trends?.categories || []).map((c) => ({ label: c.category, value: c.count }))} />
        </div>
        <div className="card p-6">
          <h2 className="mb-3 text-sm font-semibold text-ink">Acknowledgement status</h2>
          <BarChart
            data={(trends?.statuses || []).map((s) => ({ label: s.status, value: s.count }))}
            color="bg-status-read"
          />
        </div>
      </div>

      {/* Per-department (FR-31) */}
      <div className="card overflow-x-auto p-6">
        <h2 className="mb-3 text-sm font-semibold text-ink">Compliance by department</h2>
        <table className="w-full min-w-[520px] text-sm">
          <thead className="border-b border-ink-line text-left text-xs uppercase tracking-wide text-ink-muted">
            <tr><th className="py-2 font-medium">Department</th><th className="font-medium">Acknowledged</th><th className="font-medium">Pending</th><th className="font-medium">Overdue</th><th className="font-medium">Rate</th></tr>
          </thead>
          <tbody className="divide-y divide-ink-line">
            {(overview?.by_department || []).map((d) => (
              <tr key={d.department} className="hover:bg-ink-surface/60">
                <td className="py-2 font-medium text-ink">{d.department}</td>
                <td className="text-status-ack">{d.acknowledged}/{d.total}</td>
                <td>{d.pending}</td>
                <td className="text-status-unread">{d.overdue}</td>
                <td className="font-semibold">{d.rate}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Per-circular compliance + employee drilldown (FR-32) */}
      <div className="card overflow-x-auto p-6">
        <h2 className="mb-3 text-sm font-semibold text-ink">Circular compliance</h2>
        <table className="w-full min-w-[560px] text-sm">
          <thead className="border-b border-ink-line text-left text-xs uppercase tracking-wide text-ink-muted">
            <tr><th className="py-2 font-medium">Circular</th><th className="font-medium">Acknowledged</th><th className="font-medium">Overdue</th><th className="font-medium">Rate</th><th /></tr>
          </thead>
          <tbody className="divide-y divide-ink-line">
            {circulars.map((c) => (
              <Fragment key={c.id}>
                <tr>
                  <td className="py-2">
                    <span className="font-mono text-xs text-ink-muted">{c.circular_number}</span>{" "}
                    <span className="text-ink">{c.title}</span>
                  </td>
                  <td>{c.acknowledged}/{c.total}</td>
                  <td className="text-status-unread">{c.overdue}</td>
                  <td className="font-semibold">{c.rate}%</td>
                  <td className="text-right">
                    <button onClick={() => toggle(c.id)} className="btn-ghost py-1 text-xs">
                      {expanded === c.id ? "Hide" : "Employees"}
                    </button>
                  </td>
                </tr>
                {expanded === c.id && (
                  <tr>
                    <td colSpan="5" className="bg-ink-surface px-3 py-2">
                      <div className="flex flex-wrap gap-2">
                        {employees.map((e, i) => (
                          <span key={i} className={`badge ${
                            e.status === "Acknowledged" ? "bg-green-50 text-status-ack"
                              : e.status === "Read" ? "bg-amber-50 text-status-read"
                              : "bg-red-50 text-status-unread"}`}>
                            {e.user} · {e.status}{e.is_late ? " (late)" : ""}
                          </span>
                        ))}
                        {employees.length === 0 && <span className="text-xs text-ink-muted">No recipients.</span>}
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>

      {/* AI performance (FR-35) */}
      {ai && (
        <div className="card p-6">
          <h2 className="mb-3 text-sm font-semibold text-ink">AI summarization performance</h2>
          <div className="grid gap-4 sm:grid-cols-3">
            <div>
              <div className="text-xs uppercase text-ink-muted">Summaries generated</div>
              <div className="text-2xl font-bold text-ink">{ai.summaries}</div>
            </div>
            <div>
              <div className="text-xs uppercase text-ink-muted">Avg processing time</div>
              <div className="text-2xl font-bold text-ink">{ai.avg_processing_seconds ?? "—"}s</div>
            </div>
            <div>
              <div className="text-xs uppercase text-ink-muted">Avg ROUGE</div>
              <div className="text-2xl font-bold text-ink">{ai.avg_rouge ?? "—"}</div>
            </div>
          </div>
          <div className="mt-2 text-xs text-ink-muted">
            Models: {ai.models_used?.join(", ") || "—"}
          </div>
        </div>
      )}

      {/* User overview (at end) */}
      {userStats && (
        <div className="space-y-4">
          <h2 className="text-sm font-semibold text-ink">User overview</h2>

          {/* Totals */}
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="card p-5">
              <div className="text-xs font-medium uppercase tracking-wide text-ink-muted">Total users</div>
              <div className="mt-1 text-3xl font-bold text-ink">{userStats.total}</div>
            </div>
            <div className="card p-5">
              <div className="text-xs font-medium uppercase tracking-wide text-ink-muted">Active</div>
              <div className="mt-1 text-3xl font-bold text-status-ack">{userStats.active}</div>
            </div>
            <div className="card p-5">
              <div className="text-xs font-medium uppercase tracking-wide text-ink-muted">Inactive</div>
              <div className="mt-1 text-3xl font-bold text-ink-muted">{userStats.inactive}</div>
            </div>
          </div>

          {/* By role + by department */}
          <div className="grid gap-4 lg:grid-cols-2">
            <div className="card p-6">
              <h3 className="mb-3 text-sm font-semibold text-ink">Users by role</h3>
              <table className="w-full text-sm">
                <tbody className="divide-y divide-ink-line">
                  {userStats.by_role.map((r) => (
                    <tr key={r.role}>
                      <td className="py-2 text-ink">{r.role}</td>
                      <td className="py-2 text-right font-semibold text-ink">{r.count}</td>
                      <td className="w-1/2 py-2 pl-3">
                        <div className="h-2 overflow-hidden rounded-full bg-ink-surface">
                          <div className="h-full bg-brand-500"
                            style={{ width: `${userStats.total ? (100 * r.count) / userStats.total : 0}%` }} />
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="card p-6">
              <h3 className="mb-3 text-sm font-semibold text-ink">Users by department</h3>
              <table className="w-full text-sm">
                <tbody className="divide-y divide-ink-line">
                  {userStats.by_department.map((d) => (
                    <tr key={d.department}>
                      <td className="py-2 text-ink">{d.department}</td>
                      <td className="py-2 text-right font-semibold text-ink">{d.count}</td>
                      <td className="w-1/2 py-2 pl-3">
                        <div className="h-2 overflow-hidden rounded-full bg-ink-surface">
                          <div className="h-full bg-status-read"
                            style={{ width: `${userStats.total ? (100 * d.count) / userStats.total : 0}%` }} />
                        </div>
                      </td>
                    </tr>
                  ))}
                  {userStats.by_department.length === 0 && (
                    <tr><td className="py-3 text-ink-muted">No departments.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
