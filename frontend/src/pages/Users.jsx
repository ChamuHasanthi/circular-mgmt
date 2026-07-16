import { useEffect, useState } from "react";
import client from "../api/client";

// Admin user management (FR-02 roles, FR-05 department assignment).
const ROLES = ["Employee", "Manager", "Compliance Officer", "Administrator"];
const EMPTY_FORM = {
  username: "",
  email: "",
  full_name: "",
  role: "Employee",
  department_id: "",
  password: "",
};

export default function Users() {
  const [users, setUsers] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [categories, setCategories] = useState([]);
  const [form, setForm] = useState(EMPTY_FORM);
  const [deptForm, setDeptForm] = useState({ name: "", code: "" });
  const [catName, setCatName] = useState("");
  const [query, setQuery] = useState("");
  const [filterRole, setFilterRole] = useState("");
  const [filterDept, setFilterDept] = useState("");
  const [filterStatus, setFilterStatus] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    const [u, d, c] = await Promise.all([
      client.get("/users"),
      client.get("/users/departments"),
      client.get("/circulars/categories"),
    ]);
    setUsers(u.data);
    setDepartments(d.data);
    setCategories(c.data);
  }

  async function addCategory(e) {
    e.preventDefault();
    setError("");
    try {
      await client.post("/circulars/categories", { name: catName.trim() });
      setCatName("");
      await load();
    } catch (err) {
      setError(err.response?.data?.error || "Failed to add category.");
    }
  }

  async function deleteCategory(c) {
    if (!window.confirm(`Delete category "${c.name}"?`)) return;
    setError("");
    try {
      await client.delete(`/circulars/categories/${c.id}`);
      await load();
    } catch (err) {
      setError(err.response?.data?.error || "Failed to delete category.");
    }
  }

  useEffect(() => {
    load().catch(() => setError("Failed to load users."));
  }, []);

  async function createUser(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await client.post("/users", {
        ...form,
        department_id: form.department_id ? Number(form.department_id) : null,
      });
      setForm(EMPTY_FORM);
      await load();
    } catch (err) {
      setError(err.response?.data?.error || "Failed to create user.");
    } finally {
      setBusy(false);
    }
  }

  async function patchUser(id, changes) {
    await client.patch(`/users/${id}`, changes);
    await load();
  }

  async function addDepartment(e) {
    e.preventDefault();
    setError("");
    try {
      await client.post("/users/departments", {
        name: deptForm.name.trim(),
        code: deptForm.code.trim(),
      });
      setDeptForm({ name: "", code: "" });
      await load();
    } catch (err) {
      setError(err.response?.data?.error || "Failed to add department.");
    }
  }

  async function deleteDepartment(d) {
    if (!window.confirm(`Delete department "${d.name}"? Its users will be unassigned.`)) return;
    setError("");
    try {
      await client.delete(`/users/departments/${d.id}`);
      await load();
    } catch (err) {
      setError(err.response?.data?.error || "Failed to delete department.");
    }
  }

  const filteredUsers = users.filter((u) => {
    const q = query.trim().toLowerCase();
    if (q && !(`${u.full_name} ${u.username} ${u.email}`.toLowerCase().includes(q))) return false;
    if (filterRole && u.role !== filterRole) return false;
    if (filterDept && String(u.department_id || "") !== filterDept) return false;
    if (filterStatus === "active" && !u.is_active) return false;
    if (filterStatus === "inactive" && u.is_active) return false;
    return true;
  });

  async function toggleActive(u) {
    const action = u.is_active ? "deactivate" : "activate";
    try {
      await client.post(`/users/${u.id}/${action}`);
      await load();
    } catch (err) {
      setError(err.response?.data?.error || "Action failed.");
    }
  }

  return (
    <div className="space-y-5">
      <div>
        <div className="text-xs font-semibold uppercase tracking-wide text-brand-600">
          Administration
        </div>
        <h1 className="text-xl font-bold text-ink">User Management</h1>
      </div>

      {error && (
        <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-status-unread">{error}</div>
      )}

      {/* Create user */}
      <form onSubmit={createUser} className="card grid gap-3 p-5 sm:grid-cols-2 lg:grid-cols-3">
        <input className="input" placeholder="Username" value={form.username}
          onChange={(e) => setForm({ ...form, username: e.target.value })} required />
        <input className="input" type="email" placeholder="Email" value={form.email}
          onChange={(e) => setForm({ ...form, email: e.target.value })} required />
        <input className="input" placeholder="Full name" value={form.full_name}
          onChange={(e) => setForm({ ...form, full_name: e.target.value })} required />
        <select className="input" value={form.role}
          onChange={(e) => setForm({ ...form, role: e.target.value })}>
          {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
        </select>
        <select className="input" value={form.department_id}
          onChange={(e) => setForm({ ...form, department_id: e.target.value })}>
          <option value="">— Department —</option>
          {departments.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
        </select>
        <input className="input" type="password" placeholder="Temp password (8+ chars)"
          value={form.password}
          onChange={(e) => setForm({ ...form, password: e.target.value })} required />
        <div className="sm:col-span-2 lg:col-span-3">
          <button type="submit" disabled={busy} className="btn-primary">
            {busy ? "Adding…" : "Add user"}
          </button>
        </div>
      </form>

      {/* Add department */}
      <form onSubmit={addDepartment} className="card flex flex-wrap items-end gap-3 p-5">
        <div className="flex-1 min-w-[10rem]">
          <label className="mb-1 block text-xs font-medium uppercase text-ink-muted">Department name</label>
          <input className="input" placeholder="e.g. Compliance" value={deptForm.name}
            onChange={(e) => setDeptForm({ ...deptForm, name: e.target.value })} required />
        </div>
        <div className="w-32">
          <label className="mb-1 block text-xs font-medium uppercase text-ink-muted">Code</label>
          <input className="input" placeholder="e.g. COMP" value={deptForm.code}
            onChange={(e) => setDeptForm({ ...deptForm, code: e.target.value })} required />
        </div>
        <button type="submit" className="btn-ghost">+ Add department</button>
        <span className="text-xs text-ink-muted">{departments.length} departments</span>
        {departments.length > 0 && (
          <div className="w-full flex flex-wrap gap-2 border-t border-ink-line pt-3">
            {departments.map((d) => (
              <span key={d.id} className="badge bg-ink-surface text-ink">
                {d.name} <span className="text-ink-muted">({d.code})</span>
                <button type="button" onClick={() => deleteDepartment(d)}
                  className="ml-1 text-ink-muted hover:text-status-unread" title="Delete department">✕</button>
              </span>
            ))}
          </div>
        )}
      </form>

      {/* Manage categories */}
      <form onSubmit={addCategory} className="card flex flex-wrap items-end gap-3 p-5">
        <div className="flex-1 min-w-[10rem]">
          <label className="mb-1 block text-xs font-medium uppercase text-ink-muted">Category name</label>
          <input className="input" placeholder="e.g. Liquidity Risk" value={catName}
            onChange={(e) => setCatName(e.target.value)} required />
        </div>
        <button type="submit" className="btn-ghost">+ Add category</button>
        <span className="text-xs text-ink-muted">{categories.length} categories</span>
        {categories.length > 0 && (
          <div className="w-full flex flex-wrap gap-2 border-t border-ink-line pt-3">
            {categories.map((c) => (
              <span key={c.id} className="badge bg-brand-50 text-brand-700">
                {c.name}
                <button type="button" onClick={() => deleteCategory(c)}
                  className="ml-1 text-brand-400 hover:text-status-unread" title="Delete category">✕</button>
              </span>
            ))}
          </div>
        )}
      </form>

      {/* Search + filters */}
      <div className="flex flex-wrap items-center gap-2">
        <input className="input max-w-xs" placeholder="Search name, username, email…"
          value={query} onChange={(e) => setQuery(e.target.value)} />
        <select className="input" value={filterRole} onChange={(e) => setFilterRole(e.target.value)}>
          <option value="">All roles</option>
          {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
        </select>
        <select className="input" value={filterDept} onChange={(e) => setFilterDept(e.target.value)}>
          <option value="">All departments</option>
          {departments.map((d) => <option key={d.id} value={String(d.id)}>{d.name}</option>)}
        </select>
        <select className="input" value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}>
          <option value="">All statuses</option>
          <option value="active">Active</option>
          <option value="inactive">Inactive</option>
        </select>
        <span className="text-sm text-ink-muted">
          {filteredUsers.length} of {users.length}
        </span>
      </div>

      {/* Users table */}
      <div className="card table-wrap">
        <table className="w-full min-w-[720px] text-sm">
          <thead className="bg-ink-surface text-left text-xs uppercase text-ink-muted">
            <tr>
              <th className="px-4 py-3 font-medium">User</th>
              <th className="px-4 py-3 font-medium">Role</th>
              <th className="px-4 py-3 font-medium">Department</th>
              <th className="px-4 py-3 font-medium">Status</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody className="divide-y divide-ink-line">
            {filteredUsers.length === 0 ? (
              <tr><td colSpan={5} className="px-4 py-8 text-center text-ink-muted">No users match.</td></tr>
            ) : filteredUsers.map((u) => (
              <tr key={u.id} className={u.is_active ? "" : "opacity-50"}>
                <td className="px-4 py-3">
                  <div className="font-medium text-ink">{u.full_name}</div>
                  <div className="text-xs text-ink-muted">{u.username} · {u.email}</div>
                </td>
                <td className="px-4 py-3">
                  <select
                    className="input py-1 text-xs"
                    value={u.role}
                    onChange={(e) => patchUser(u.id, { role: e.target.value })}
                  >
                    {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
                  </select>
                </td>
                <td className="px-4 py-3">
                  <select
                    className="input py-1 text-xs"
                    value={u.department_id || ""}
                    onChange={(e) =>
                      patchUser(u.id, {
                        department_id: e.target.value ? Number(e.target.value) : null,
                      })
                    }
                  >
                    <option value="">—</option>
                    {departments.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
                  </select>
                </td>
                <td className="px-4 py-3">
                  <span className={`badge ${u.is_active
                    ? "bg-green-50 text-status-ack"
                    : "bg-red-50 text-status-unread"}`}>
                    {u.is_active ? "Active" : "Inactive"}
                  </span>
                </td>
                <td className="px-4 py-3 text-right">
                  <button onClick={() => toggleActive(u)} className="btn-ghost py-1.5 text-xs">
                    {u.is_active ? "Deactivate" : "Activate"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
