# Chapters 3 & 4 — As-Built Prose (authoritative, current)

> Regenerated to reflect the system exactly as implemented (including the RAG
> relevance gate, four-eyes approval workflow, amendment/supersede handling and
> the acronym-glossary prompt hint). Edit freely — this replaces any earlier
> reconstruction. Requirement IDs (FR-xx / NFR-xx) match the SRS.

---

# Chapter 3 — Methodology

## 3.1 Research approach

This project follows a **Design Science Research (DSR)** approach: the primary
output is an *artefact* — a working software system — built to solve a real
organisational problem (the manual, slow and error-prone handling of Central
Bank of Sri Lanka (CBSL) regulatory circulars in a commercial bank), and then
evaluated against objective criteria. DSR is appropriate here because the
contribution is not a new theory but a demonstrably useful, evaluated system
that combines existing NLP techniques in a novel, domain-specific pipeline.

The work proceeds through the classic DSR cycle: (1) problem identification and
requirements elicitation, (2) design and development of the artefact, (3)
demonstration on real circulars, and (4) evaluation against summarization
quality, retrieval accuracy, faithfulness and latency metrics.

## 3.2 Development methodology

An **incremental, phase-based** development methodology was adopted. The system
was decomposed into eight self-contained phases (Phase 0–7: environment setup,
authentication/RBAC, upload & PDF extraction, AI summarization,
classification & distribution, search & live views, RAG chatbot, and analytics),
each producing a working, testable increment. This suited a single-developer
final-year project: it kept scope controlled, allowed the most technically risky
components (local LLM summarization and RAG retrieval) to be built and validated
early, and let requirements be refined against a running system rather than only
on paper.

## 3.3 Requirements engineering

Requirements were captured as numbered **functional requirements (FR-xx)** and
**non-functional requirements (NFR-xx)** and maintained in a
requirements-traceability matrix (Appendix X) that links each requirement to the
module and test that satisfies it. Key drivers were:

- **NFR-08 (data privacy):** all AI inference must run **locally / offline** — no
  bank regulatory data may be sent to a third-party cloud API. This single
  constraint shaped almost every AI design decision in Chapter 4.
- **Governance:** regulatory publication must not be fully automated; a human
  must approve every summary before it reaches staff (motivating the four-eyes
  workflow, FR-30s).
- **Usability:** non-technical compliance staff must be able to find, understand
  and act on circulars quickly (motivating summarization and the chatbot).

## 3.4 Methodology for the AI components

### 3.4.1 Summarization

Because of NFR-08, cloud LLMs (GPT-4, Claude, Gemini) were excluded. The
methodology instead uses a **local instruction-tuned LLM** — Llama 3.2 3B served
through **Ollama** — with an **extractive-abstractive fallback (BART,
`facebook/bart-large-cnn`)** for when the LLM is unavailable. Faithfulness to the
source is prioritised over fluency through **prompt engineering** rather than
fine-tuning (which was infeasible on the available hardware): the prompt
constrains the model to use only stated information, preserve exact figures and
dates, avoid echoing the source, and — following an observed error — use a
**domain glossary** of correct banking-acronym expansions (e.g. LGD = Loss Given
Default) rather than guessing.

### 3.4.2 Retrieval-augmented chatbot

The chatbot uses **Retrieval-Augmented Generation (RAG)**: rather than relying on
the LLM's parametric memory (which would hallucinate), every answer is grounded
in text retrieved from the published circulars. The retrieval methodology is
**hybrid**: dense semantic search (Sentence-BERT `all-MiniLM-L6-v2` embeddings in
a FAISS inner-product index) is fused with sparse lexical search (a custom BM25)
via **Reciprocal Rank Fusion (RRF, k=60)**. Dense retrieval captures paraphrase;
BM25 captures exact regulatory tokens (acronyms, circular numbers, "14 days")
that embeddings blur. A **relevance gate** (a minimum cosine-similarity
threshold) rejects out-of-scope questions before generation, so the bot answers
"I could not find that in the circulars" instead of hallucinating.

## 3.5 Evaluation methodology

Four complementary evaluations were designed:

1. **Summarization quality** — automatic **ROUGE** (lexical overlap) and
   **BERTScore** (semantic similarity) against human-written reference summaries.
2. **Faithfulness** — a manual spot-check of ~10 summaries, each verified clause
   by clause against the *complete* source document and labelled
   Faithful / Unfaithful, since ROUGE/BERTScore reward overlap but not factual
   correctness.
3. **RAG accuracy** — an automated harness (`eval_rag.py`) over a labelled
   question set reporting (a) **global retrieval hit-rate** (did the correct
   circular appear in the citations?) and (b) **scoped answer accuracy** (did the
   answer contain an acceptable keyword?), with a stem-aware, OR-list keyword
   matcher to avoid penalising correct-but-differently-worded answers.
4. **Performance** — wall-clock **latency** (seconds per summary, seconds per chat
   response) on the target hardware (§6.7), establishing feasibility on modest
   on-premise equipment.

## 3.6 Tools and technologies

Python 3.10 / Flask (application-factory + blueprints) and SQLAlchemy over
**MySQL 8** (XAMPP) for the backend; **React 18 + Vite + Tailwind CSS** for the
SPA frontend; JWT (Flask-JWT-Extended) with bcrypt (work factor 12) for auth;
PyMuPDF + Tesseract OCR for extraction; spaCy, Sentence-BERT, FAISS, Ollama for
AI. All model weights are cached locally for offline operation (NFR-08).

---

# Chapter 4 — System Design

## 4.1 Design overview

The system is a **three-tier web application**: a React single-page frontend, a
Flask REST API, and a MySQL database, with a set of **local AI services**
(Ollama LLM, Sentence-BERT/FAISS, spaCy, Tesseract) invoked by the API tier. All
tiers run **on-premise / offline** to satisfy NFR-08.

## 4.2 Architecture

```
[ React SPA ]  --HTTPS/JWT-->  [ Flask REST API ]  --SQLAlchemy-->  [ MySQL 8 ]
                                      |
                                      +--> AI Engine (local, offline)
                                             - PyMuPDF + Tesseract (extract/OCR)
                                             - Ollama / Llama 3.2 3B (+ BART fallback)
                                             - Sentence-BERT + FAISS + BM25 (RAG)
                                             - spaCy (entities/keywords)
```

The Flask API is organised into **blueprints** by concern (auth, circulars,
users, audit, dashboard, chat). The **AI Engine** is a separate module layer so
that models load lazily and can be swapped or disabled by configuration without
touching the API. This separation also isolates the heavy, slow AI calls from
the fast CRUD path.

## 4.3 Roles and access control (RBAC)

Four roles enforce separation of duties:

| Role | Responsibilities |
|---|---|
| **Administrator** | User & department/category management, audit log |
| **Manager** | Oversight, analytics dashboard |
| **Compliance Officer** | Approves/rejects summaries (the "checker") |
| **Employee** | Reads, acknowledges and queries published circulars |

RBAC is enforced server-side on every protected endpoint via JWT-claim checks,
never in the frontend alone.

## 4.4 Circular lifecycle (state model)

A circular moves through an explicit state machine that encodes the governance
requirement that no summary is published without human approval:

```
uploaded → processing → review → pending_approval → published
                    \→ failed
```

- **uploaded → processing:** text extraction (PyMuPDF, OCR fallback).
- **processing → review:** AI summary generated; the maker edits/verifies it.
- **review → pending_approval:** the maker submits for approval.
- **pending_approval → published:** a *different* user (Compliance Officer) — the
  checker — approves it (**four-eyes / maker-checker**, FR-30s). Rejection
  returns it to review with a recorded reason.

## 4.5 Data model (ERD)

Core entities:

- **User** (id, name, email, password_hash, role, department_id, active)
- **Department** and **Category** (classification targets)
- **Circular** (id, circular_number, title, status, extracted_text, uploaded_by,
  **approved_by**, **approved_at**, **amends_circular_id**, distribution_intent)
- **Summary** (id, circular_id **[UNIQUE]**, summary_text) — the UNIQUE constraint
  guarantees one summary per circular, preventing the duplicate-summary defect.
- **Acknowledgement** (user_id, circular_id, status) — tracks read/confirmed.
- **AuditLog** (actor, action, target, timestamp) — accountability (NFR).

`amends_circular_id` is a self-reference on Circular: an amending circular points
to the one it supersedes, which drives both the "Updated by" UI banner and the
retrieval demotion of superseded text.

## 4.6 Summarization design

The pipeline extracts text (header/table-artefact aware), then attempts a local
LLM summary sized to the source (target ≈ source_words/3, clamped 150–450 words),
falling back to BART on timeout/unavailability. Output is normalised to a fixed
**Overview + Key Points** structure. Faithfulness is enforced by the constrained
prompt described in §3.4.1, including the acronym glossary.

## 4.7 RAG chatbot design

Published circulars are chunked (200 words, 50-word overlap, newline-preserving),
embedded with Sentence-BERT and stored in a persisted FAISS index rebuilt on each
publish. At query time (FR-37):

1. The query is optionally rewritten by the LLM (typo/word-split repair).
2. **Hybrid retrieval** — dense (FAISS) + sparse (BM25) fused by **RRF (k=60)**;
   superseded chunks are demoted (×0.85) so current circulars win.
3. **Relevance gate** — in global search, if the best chunk's cosine similarity
   is below `RAG_MIN_RELEVANCE` (0.25), the system returns a "not found" reply
   without invoking the LLM (rejecting off-topic questions). Measured separation:
   on-topic queries 0.53–0.63, off-topic 0.07–0.21.
4. **Grounded generation** — the LLM answers strictly from the retrieved chunks,
   with citations; an extractive QA reader is the fallback.

Per-circular chat (a chosen circular) skips the gate and always answers from that
document's chunks.

## 4.8 Frontend design

A role-aware React SPA (React Router) with a responsive layout (collapsible
mobile drawer, gradient sidebar). Key views: dashboards (Manager/Employee),
approval queue, circular summary (with approve/reject dialog and "Updated by"
banner), audit log, user/department/category management, and a chat panel
(maximisable, multi-conversation, citation links). JWT is held in localStorage
with a 60-minute idle timeout (FR-03).

## 4.9 Security & non-functional design

bcrypt-hashed passwords (factor 12); JWT with 60-minute expiry; server-side RBAC;
input validation and file-type/size limits on upload; an immutable audit trail;
and — the defining NFR — **fully local AI inference** so no regulatory content
leaves the bank's infrastructure (NFR-08).

## 4.10 Deployment

The system was deployed to a **Linux VPS managed through aaPanel**, served
publicly over HTTPS at `circular.chamudikahasanthi.com`. All three tiers — the
React frontend, the Flask API and the local AI runtime — run on the **same
on-premise server**, preserving the offline-inference requirement (NFR-08): no
regulatory content or model call leaves the host.

**Deployment architecture.** A single Nginx instance is the public entry point
and reverse proxy. Requests to `/api/` are proxied to the Flask backend on
`127.0.0.1:5000`; all other routes are served by the built React single-page
application. Long proxy timeouts (900 s) are set on the API location so slow
local-LLM summarization requests are not cut off, and `client_max_body_size 20M`
enforces the upload limit at the proxy layer.

```
Internet ── HTTPS ──► Nginx (aaPanel)
                        ├── /api/  ──► Flask API      (127.0.0.1:5000, Supervisor)
                        └── /      ──► React dist SPA  (127.0.0.1:5173, PM2)
                                            │
                                            └── Ollama (127.0.0.1:11434, Llama 3.2 3B)
```

**Database.** The production database is **MySQL 8**, with the connection string
supplied through the backend `.env` `DATABASE_URL` variable (the SQLite value
sometimes shown in setup notes is only an illustrative placeholder). SQLAlchemy
abstracts the driver, so the same application code runs unchanged against MySQL.

**Backend runtime.** The Flask application runs under a Python 3.12 virtual
environment and is kept alive by **aaPanel Supervisor** (process
`circular-backend`, run user `www`, autostart and autorestart enabled), which
restarts it automatically on failure or reboot. Runtime dependencies include
FAISS (`faiss-cpu`), PyMuPDF and pytesseract, with **Tesseract OCR** installed at
system level for scanned-PDF fallback. The Sentence-BERT embedding model
(`all-MiniLM-L6-v2`) is pre-downloaded into a local Hugging Face cache so the
chatbot operates fully offline, and the `llama3.2:3b` model is pulled locally
through **Ollama**.

**Frontend runtime.** The React application is compiled to static assets
(`npm run build`) and served by **PM2** in SPA mode (`circular-frontend`), with
`pm2 save` / `pm2 startup` ensuring it restarts on reboot.

**File permissions.** The `www` service user was granted write access to the
FAISS index directory (`app/ai/index_store`) and the `uploads` folder, resolving
a `PermissionError` that initially prevented the chatbot from persisting its
vector index.

**Deployment issues resolved.** Missing runtime modules were installed during
commissioning — PyMuPDF (`fitz`), `faiss-cpu`, and the Sentence-BERT model cache
— and the index-store permission error above was corrected before final
verification against the public URL.
