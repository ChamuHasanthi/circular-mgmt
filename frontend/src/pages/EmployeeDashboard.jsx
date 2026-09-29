import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import client from "../api/client";
import StatusBadge from "../components/StatusBadge.jsx";
import ChatPanel from "../components/ChatPanel.jsx";
import Icon from "../components/Icon.jsx";
import { useAuth } from "../context/AuthContext.jsx";

// WF-02 — circular list view (FR-27–29). Live data, search + filters.
// Employees see only their assigned circulars + their acknowledgement status;
// Managers/Administrators see all circulars + the publication status, and can
// manage them (admin: edit/delete · manager: flag a problem).
const STATUSES = ["Unread", "Read", "Acknowledged"];
// Employee-facing labels (stored values unchanged).
const STATUS_LABEL = { Unread: "New", Read: "Read", Acknowledged: "Confirmed" };

const PRIORITY_STYLE = {
  High: "bg-red-50 text-status-unread",
  Medium: "bg-amber-50 text-status-read",
  Low: "bg-slate-100 text-ink-muted",
};
const LIFECYCLE_STYLE = {
  published: "bg-green-50 text-status-ack",
  processing: "bg-blue-50 text-blue-700",
  pending_approval: "bg-blue-50 text-blue-700",
  review: "bg-amber-50 text-status-read",
  uploaded: "bg-amber-50 text-status-read",
  failed: "bg-red-50 text-status-unread",
};
const EMPTY_EDIT = { id: null, circular_number: "", title: "", issue_date: "", priority: "Medium" };

export default function EmployeeDashboard() {
  const { user } = useAuth();
  const isAdmin = user?.role === "Administrator";
  const isManager = user?.role === "Manager";
  const isStaff = isAdmin || isManager;

  const [items, setItems] = useState([]);
  const [categories, setCategories] = useState([]);
  const [q, setQ] = useState("");
  const [category, setCategory] = useState("");
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState("");

  const [edit, setEdit] = useState(null);      // circular being edited
  const [flag, setFlag] = useState(null);      // circular being flagged
  const [flagMsg, setFlagMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);  // global assistant drawer

  async function load() {
    setLoading(true);
    const params = {};
    if (q.trim()) params.q = q.trim();
    if (category) params.category = category;
    if (status) params.status = status;
    try {
      const res = await client.get("/circulars", { params });
      setItems(res.data);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [category, status]);

  useEffect(() => {
    client.get("/circulars/categories")
      .then((res) => setCategories(res.data))
      .catch(() => flash("Could not load categories."));
  }, []);

  function flash(text) {
    setMsg(text);
    setTimeout(() => setMsg(""), 4000);
  }

  async function saveEdit(e) {
    e.preventDefault();
    setBusy(true);
    try {
      await client.patch(`/circulars/${edit.id}`, {
        circular_number: edit.circular_number,
        title: edit.title,
        issue_date: edit.issue_date,
        priority: edit.priority,
        amends_circular_id: edit.amends_circular_id || null,
      });
      setEdit(null);
      await load();
      flash("Circular updated.");
    } catch (err) {
      flash(err.response?.data?.error || "Update failed.");
    } finally {
      setBusy(false);
    }
  }

  async function remove(c) {
    if (!window.confirm(`Delete circular ${c.circular_number}? This cannot be undone.`)) return;
    try {
      await client.delete(`/circulars/${c.id}`);
      await load();
      flash(`Circular ${c.circular_number} deleted.`);
    } catch (err) {
      flash(err.response?.data?.error || "Delete failed.");
    }
  }

  async function submitFlag(e) {
    e.preventDefault();
    setBusy(true);
    try {
      await client.post(`/circulars/${flag.id}/request`, { message: flagMsg });
      setFlag(null);
      setFlagMsg("");
      flash("Your request has been sent to the administrators.");
    } catch (err) {
      flash(err.response?.data?.error || "Could not send request.");
    } finally {
      setBusy(false);
    }
  }

  const colSpan = isStaff ? 6 : 6;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-ink">
            {isStaff ? "All Circulars" : "My Circulars"}
          </h1>
          {!loading && (
            <p className="mt-0.5 text-sm text-ink-muted">
              {items.length} circular{items.length === 1 ? "" : "s"}
            </p>
          )}
        </div>
        <form
          onSubmit={(e) => { e.preventDefault(); load(); }}
          className="flex flex-wrap items-center gap-2"
        >
          <input className="input max-w-xs" placeholder="Search title, number, summary…"
            value={q} onChange={(e) => setQ(e.target.value)} />
          <select className="input" value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="">All categories</option>
            {categories.map((c) => <option key={c.id} value={c.name}>{c.name}</option>)}
          </select>
          {!isStaff && (
            <select className="input" value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">All statuses</option>
              {STATUSES.map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}
            </select>
          )}
          <button type="submit" className="btn-primary">Search</button>
        </form>
      </div>

      {msg && (
        <div className="rounded-lg bg-brand-50 px-3 py-2 text-sm text-brand-700">{msg}</div>
      )}

      <div className="card table-wrap">
        <table className="w-full min-w-[720px] text-sm">
          <thead className="bg-ink-surface text-left text-xs uppercase text-ink-muted">
            <tr>
              <th className="px-4 py-3 font-medium">Circular</th>
              <th className="px-4 py-3 font-medium">Title</th>
              <th className="px-4 py-3 font-medium">Category</th>
              <th className="px-4 py-3 font-medium">Priority</th>
              <th className="px-4 py-3 font-medium">Status</th>
              <th className="px-4 py-3 text-right font-medium">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-ink-line">
            {loading ? (
              <tr><td colSpan={colSpan} className="px-4 py-8 text-center text-ink-muted">Loading…</td></tr>
            ) : items.length === 0 ? (
              <tr><td colSpan={colSpan} className="px-4 py-8 text-center text-ink-muted">No circulars found.</td></tr>
            ) : (
              items.map((c) => (
                <tr key={c.id} className="hover:bg-ink-surface/60">
                  <td className="px-4 py-3 font-mono text-xs text-ink-muted">{c.circular_number}</td>
                  <td className="px-4 py-3 font-medium text-ink">
                    {c.title}
                    {c.is_superseded && c.amended_by && (
                      <span className="ml-2 badge bg-amber-50 text-status-read">
                        Updated by {c.amended_by.circular_number}
                      </span>
                    )}
                    {c.amends && (
                      <span className="ml-2 badge bg-slate-100 text-ink-muted">
                        Amends {c.amends.circular_number}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1">
                      {c.categories?.map((cat) => (
                        <span key={cat} className="badge bg-brand-50 text-brand-700">{cat}</span>
                      ))}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`badge ${PRIORITY_STYLE[c.priority] || "bg-slate-100 text-ink-muted"}`}>
                      {c.priority}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    {isStaff ? (
                      <span className={`badge capitalize ${LIFECYCLE_STYLE[c.status] || "bg-slate-100 text-ink-muted"}`}>
                        {c.status}
                      </span>
                    ) : c.my_status ? (
                      <StatusBadge status={c.my_status} />
                    ) : (
                      <span className="text-xs text-ink-muted">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-end gap-2">
                      <Link to={`/circulars/${c.id}`} className="btn-ghost py-1.5 text-xs">Open</Link>
                      {isManager && (
                        <button onClick={() => { setFlag(c); setFlagMsg(""); }}
                          className="btn-ghost py-1.5 text-xs text-status-read">Flag</button>
                      )}
                      {isAdmin && (
                        <>
                          <button
                            onClick={() => setEdit({
                              id: c.id, circular_number: c.circular_number, title: c.title,
                              issue_date: c.issue_date || "", priority: c.priority,
                              amends_circular_id: c.amends_circular_id || "",
                            })}
                            className="btn-ghost py-1.5 text-xs">Edit</button>
                          <button onClick={() => remove(c)}
                            className="btn-ghost py-1.5 text-xs text-status-unread">Delete</button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Edit modal (admin) */}
      {edit && (
        <Modal title="Edit circular" onClose={() => setEdit(null)}>
          <form onSubmit={saveEdit} className="space-y-3">
            <Field label="Circular number">
              <input className="input" value={edit.circular_number}
                onChange={(e) => setEdit({ ...edit, circular_number: e.target.value })} required />
            </Field>
            <Field label="Title">
              <input className="input" value={edit.title}
                onChange={(e) => setEdit({ ...edit, title: e.target.value })} required />
            </Field>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <Field label="Issue date">
                <input type="date" className="input" value={edit.issue_date || ""}
                  onChange={(e) => setEdit({ ...edit, issue_date: e.target.value })} />
              </Field>
              <Field label="Priority">
                <select className="input" value={edit.priority}
                  onChange={(e) => setEdit({ ...edit, priority: e.target.value })}>
                  <option>High</option><option>Medium</option><option>Low</option>
                </select>
              </Field>
            </div>
            <Field label="Amends an earlier circular (optional)">
              <select className="input" value={edit.amends_circular_id || ""}
                onChange={(e) => setEdit({ ...edit, amends_circular_id: e.target.value })}>
                <option value="">— None —</option>
                {items.filter((c) => c.id !== edit.id).map((c) => (
                  <option key={c.id} value={c.id}>{c.circular_number} — {c.title}</option>
                ))}
              </select>
            </Field>
            <div className="flex justify-end gap-2 pt-2">
              <button type="button" onClick={() => setEdit(null)} className="btn-ghost">Cancel</button>
              <button type="submit" disabled={busy} className="btn-primary">
                {busy ? "Saving…" : "Save changes"}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {/* Flag modal (manager) */}
      {flag && (
        <Modal title={`Flag circular ${flag.circular_number}`} onClose={() => setFlag(null)}>
          <form onSubmit={submitFlag} className="space-y-3">
            <p className="text-sm text-ink-muted">
              Describe the problem. Administrators will be notified to review it.
            </p>
            <textarea className="input h-28" placeholder="e.g. Wrong category, should be archived…"
              value={flagMsg} onChange={(e) => setFlagMsg(e.target.value)} required />
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setFlag(null)} className="btn-ghost">Cancel</button>
              <button type="submit" disabled={busy} className="btn-primary">
                {busy ? "Sending…" : "Send request"}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {/* Global RAG assistant — ask about any circular (FR-36–39) */}
      {chatOpen ? (
        <div className="fixed bottom-4 right-4 z-40 w-[22rem] max-w-[calc(100vw-2rem)] shadow-card">
          <div className="mb-2 flex justify-end">
            <button
              onClick={() => setChatOpen(false)}
              className="grid h-8 w-8 place-items-center rounded-full border border-ink-line bg-white text-sm text-ink hover:bg-ink-surface"
              title="Close assistant"
            >
              ✕
            </button>
          </div>
          <ChatPanel />
        </div>
      ) : (
        <button
          onClick={() => setChatOpen(true)}
          className="btn-primary fixed bottom-6 right-6 z-40 flex items-center gap-2 rounded-full px-4 py-3 shadow-card"
          title="Ask the Circular Assistant"
        >
          <Icon name="chat" className="h-5 w-5" />
          <span className="hidden sm:inline">Assistant</span>
        </button>
      )}
    </div>
  );
}

function Modal({ title, onClose, children }) {
  return (
    <div className="fixed inset-0 z-30 grid place-items-center bg-black/30 p-4" onClick={onClose}>
      <div className="card w-full max-w-md p-6" onClick={(e) => e.stopPropagation()}>
        <h2 className="mb-4 text-lg font-bold text-ink">{title}</h2>
        {children}
      </div>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <div>
      <label className="mb-1 block text-sm font-medium text-ink">{label}</label>
      {children}
    </div>
  );
}
