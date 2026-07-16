import { useEffect, useRef, useState } from "react";
import client from "../api/client";
import EntityTags from "../components/EntityTags.jsx";
import SummaryText from "../components/SummaryText.jsx";
import PublishControls from "../components/PublishControls.jsx";
import Icon from "../components/Icon.jsx";

// WF-05 — Administrator upload screen (FR-06–FR-10).
// Real upload: metadata + PDF -> backend validates, extracts text (PyMuPDF),
// captures metadata, detects duplicates. Shows a live processing indicator and
// an extraction result card on success.
const MAX_MB = 20;
const EMPTY = { circular_number: "", title: "", issue_date: "", priority: "Medium",
                amends_circular_id: "" };

export default function AdminUpload() {
  const [form, setForm] = useState(EMPTY);
  const [existing, setExisting] = useState([]);   // circulars available to amend

  // Load existing circulars for the "amends" picker.
  useEffect(() => {
    client.get("/circulars").then((r) => setExisting(r.data)).catch(() => {});
  }, []);
  const [file, setFile] = useState(null);
  const [status, setStatus] = useState("idle"); // idle | uploading | done | error
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const fileInput = useRef(null);

  // FR-11–17 + FR-19/25: AI summarization + distribution of the uploaded circular.
  const [summarizing, setSummarizing] = useState(false);
  const [summary, setSummary] = useState(null);
  const [classifications, setClassifications] = useState([]);
  const [submitted, setSubmitted] = useState(false);
  const [sumError, setSumError] = useState("");

  async function handleSummarize() {
    setSumError("");
    setSummarizing(true);
    try {
      const res = await client.post(
        `/circulars/${result.circular.id}/summarize`,
        {},
        { timeout: 1200000 } // LLM summarization on CPU can take several minutes
      );
      setSummary(res.data.summary);
      setClassifications(res.data.classifications || []);
    } catch (err) {
      setSumError(err.response?.data?.error || "Summarization failed.");
    } finally {
      setSummarizing(false);
    }
  }

  function pickFile(f) {
    setError("");
    if (!f) return;
    if (!f.name.toLowerCase().endsWith(".pdf")) {
      setError("Only PDF files are accepted.");
      return;
    }
    if (f.size > MAX_MB * 1024 * 1024) {
      setError(`File exceeds the ${MAX_MB}MB limit.`);
      return;
    }
    setFile(f);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    if (!file) return setError("Please choose a PDF file.");
    if (!form.circular_number.trim() || !form.title.trim()) {
      return setError("Circular number and title are required.");
    }

    const data = new FormData();
    data.append("file", file);
    Object.entries(form).forEach(([k, v]) => data.append(k, v));

    setStatus("uploading");
    try {
      const res = await client.post("/circulars/upload", data, {
        headers: { "Content-Type": undefined }, // let the browser set the boundary
      });
      setResult(res.data);
      setStatus("done");
    } catch (err) {
      setError(err.response?.data?.error || "Upload failed.");
      setStatus("error");
    }
  }

  function reset() {
    setForm(EMPTY);
    setFile(null);
    setResult(null);
    setError("");
    setStatus("idle");
    setSummary(null);
    setClassifications([]);
    setSubmitted(false);
    setSumError("");
    if (fileInput.current) fileInput.current.value = "";
  }

  // ---- success view ----
  if (status === "done" && result) {
    const c = result.circular;
    const x = result.extraction;
    return (
      <div className="mx-auto max-w-2xl space-y-4">
        <h1 className="text-xl font-bold text-ink">Upload complete</h1>
        <div className="card space-y-4 p-6">
          <div className="flex items-center gap-2 text-status-ack">
            <span className="grid h-6 w-6 place-items-center rounded-full bg-green-50">
              <Icon name="check" className="h-4 w-4" />
            </span>
            <span className="text-sm font-semibold">{result.message}</span>
          </div>
          <dl className="grid grid-cols-2 gap-3 text-sm">
            <Field label="Circular number" value={c.circular_number} />
            <Field label="Priority" value={c.priority} />
            <Field label="Title" value={c.title} span />
            <Field label="Issue date" value={c.issue_date || "—"} />
            <Field label="File size" value={`${c.file_size_kb} KB`} />
            <Field label="Pages" value={x.page_count} />
            <Field label="Words extracted" value={x.word_count} />
          </dl>
          <div>
            <div className="mb-1 text-xs font-medium uppercase text-ink-muted">
              Extracted text preview
            </div>
            <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded-lg bg-ink-surface p-3 text-xs text-ink">
              {x.preview}…
            </pre>
          </div>

          {/* AI summarization (FR-11–17) — generate, review, then publish */}
          <div className="border-t border-ink-line pt-4">
            {!summary ? (
              <div className="space-y-3">
                <button onClick={handleSummarize} disabled={summarizing} className="btn-primary">
                  {summarizing ? (
                    <span className="flex items-center gap-2">
                      <span className="h-3 w-3 animate-spin rounded-full border-2 border-white border-t-transparent" />
                      Summarizing…
                    </span>
                  ) : (
                    <span className="flex items-center gap-2">
                      <Icon name="sparkles" className="h-4 w-4" />
                      Generate summary
                    </span>
                  )}
                </button>
                {summarizing && (
                  <p className="text-xs text-ink-muted">
                    First run loads the models and may take 1–2 minutes on CPU.
                  </p>
                )}
                {sumError && (
                  <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-status-unread">
                    {sumError}
                  </div>
                )}
              </div>
            ) : (
              <div className="space-y-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-semibold text-ink">AI Summary</span>
                  {!submitted && (
                    <span className="badge bg-amber-50 text-status-read">Draft — review before submitting</span>
                  )}
                  {classifications.map((c) => (
                    <span key={c.id || c.category} className="badge bg-brand-50 text-brand-700">
                      {c.category}
                    </span>
                  ))}
                  <span className="text-[11px] text-ink-muted">
                    {summary.bart_model} · {summary.word_count} words · {summary.processing_seconds}s
                  </span>
                </div>
                <div className="rounded-lg bg-ink-surface p-3 text-sm">
                  <SummaryText text={summary.summary_text} />
                </div>
                <div>
                  <div className="mb-1 text-xs font-medium uppercase text-ink-muted">
                    Key topics
                  </div>
                  <EntityTags entities={summary.entities} />
                </div>

                {/* Review step: pick category + departments, then submit for approval */}
                {!submitted ? (
                  <div className="space-y-3 border-t border-ink-line pt-3">
                    <PublishControls
                      circularId={result.circular.id}
                      defaultCategories={classifications.map((c) => c.category)}
                      onSubmitted={() => setSubmitted(true)}
                    />
                    <button onClick={handleSummarize} disabled={summarizing} className="btn-ghost">
                      {summarizing ? "Regenerating…" : "Regenerate summary"}
                    </button>
                    {sumError && (
                      <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-status-unread">
                        {sumError}
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="rounded-lg border border-ink-line bg-ink-surface p-3 text-sm">
                    <span className="font-semibold text-ink">Submitted for approval.</span>{" "}
                    A Compliance Officer will review and publish it. You'll be notified
                    of the outcome.
                  </div>
                )}
              </div>
            )}
          </div>

          <button onClick={reset} className="btn-ghost">Upload another</button>
        </div>
      </div>
    );
  }

  // ---- form view ----
  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <div>
        <h1 className="text-xl font-bold text-ink">Upload Circular</h1>
      </div>

      <form onSubmit={handleSubmit} className="card space-y-4 p-6">
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="mb-1 block text-sm font-medium text-ink">Circular number</label>
            <input className="input" placeholder="e.g. 05/2024" value={form.circular_number}
              onChange={(e) => setForm({ ...form, circular_number: e.target.value })} />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-ink">Issue date</label>
            <input type="date" className="input" value={form.issue_date}
              onChange={(e) => setForm({ ...form, issue_date: e.target.value })} />
          </div>
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium text-ink">Title</label>
          <input className="input" placeholder="Circular title" value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })} />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium text-ink">Priority</label>
          <select className="input" value={form.priority}
            onChange={(e) => setForm({ ...form, priority: e.target.value })}>
            <option>High</option><option>Medium</option><option>Low</option>
          </select>
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium text-ink">
            Amends an earlier circular <span className="text-ink-muted">(optional)</span>
          </label>
          <select className="input" value={form.amends_circular_id}
            onChange={(e) => setForm({ ...form, amends_circular_id: e.target.value })}>
            <option value="">— None —</option>
            {existing.map((c) => (
              <option key={c.id} value={c.id}>{c.circular_number} — {c.title}</option>
            ))}
          </select>
        </div>

        <div>
          <label className="mb-1 block text-sm font-medium text-ink">PDF file</label>
          <div
            onClick={() => fileInput.current?.click()}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => { e.preventDefault(); pickFile(e.dataTransfer.files?.[0]); }}
            className="grid cursor-pointer place-items-center rounded-lg border-2 border-dashed border-ink-line bg-ink-surface py-10 text-sm text-ink-muted hover:border-brand-400"
          >
            {file ? (
              <span className="flex items-center gap-2 font-medium text-ink">
                <Icon name="document" className="h-4 w-4" /> {file.name}
              </span>
            ) : (
              <span>Click or drag &amp; drop a PDF here (max {MAX_MB} MB)</span>
            )}
          </div>
          <input ref={fileInput} type="file" accept="application/pdf,.pdf" className="hidden"
            onChange={(e) => pickFile(e.target.files?.[0])} />
        </div>

        {error && (
          <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-status-unread">{error}</div>
        )}

        <button type="submit" disabled={status === "uploading"} className="btn-primary">
          {status === "uploading" ? (
            <span className="flex items-center gap-2">
              <span className="h-3 w-3 animate-spin rounded-full border-2 border-white border-t-transparent" />
              Extracting text…
            </span>
          ) : (
            "Upload & extract"
          )}
        </button>
      </form>
    </div>
  );
}

function Field({ label, value, span }) {
  return (
    <div className={span ? "col-span-2" : ""}>
      <dt className="text-xs font-medium uppercase text-ink-muted">{label}</dt>
      <dd className="text-sm text-ink">{value}</dd>
    </div>
  );
}
