import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";
import Icon from "../components/Icon.jsx";

// WF-01 — Login screen
export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  // Banner notices driven by query params (set after redirects).
  const notice = params.get("expired")
    ? "Your session expired after 30 minutes of inactivity. Please sign in again."
    : params.get("reset")
    ? "Password updated. Please sign in with your new password."
    : "";

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(username, password);
      navigate("/");
    } catch (err) {
      setError(err.response?.data?.error || "Login failed. Is the backend running?");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="relative grid min-h-screen place-items-center overflow-hidden bg-gradient-to-br from-brand-600 via-brand-700 to-brand-900 p-4">
      {/* light decorative rings (no blur — stays smooth on low-end GPUs) */}
      <div className="pointer-events-none absolute -left-20 -top-20 h-72 w-72 rounded-full border border-white/10" />
      <div className="pointer-events-none absolute -bottom-24 -right-16 h-96 w-96 rounded-full border border-white/10" />

      <div className="relative w-full max-w-md rounded-2xl border border-ink-line bg-white p-8 shadow-2xl">
        <div className="mb-6 flex flex-col items-center text-center">
          <div className="mb-3 grid h-14 w-14 place-items-center rounded-2xl bg-gradient-to-br from-brand-500 to-brand-700 shadow-md ring-1 ring-white/30">
            <Icon name="bank" className="h-7 w-7 text-white" />
          </div>
          <h1 className="text-xl font-bold tracking-tight text-ink">Circular Hub</h1>
          <p className="mt-1 text-xs text-ink-muted">
            Smart Circular Summarization &amp; Management System
          </p>
        </div>

        {notice && (
          <div className="mb-4 rounded-lg bg-amber-50 px-3 py-2 text-sm text-status-read">
            {notice}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-ink">Username</label>
            <input
              className="input"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="username"
              autoFocus
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-ink">Password</label>
            <input
              type="password"
              className="input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
            />
          </div>

          {error && (
            <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-status-unread">
              {error}
            </div>
          )}

          <button type="submit" disabled={loading} className="btn-primary w-full">
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <div className="mt-4 text-center">
          <Link to="/forgot-password" className="text-sm text-brand-600 hover:underline">
            Forgot password?
          </Link>
        </div>

         
      </div>
    </div>
  );
}
