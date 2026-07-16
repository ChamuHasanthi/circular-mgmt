"""Local LLM summariser via Ollama (offline instruction-tuned model, NFR-08).

Produces a faithful, structured summary (Overview + Key Points) from a circular
using a locally-hosted model (default llama3.2:3b). All inference stays on the
machine — Ollama exposes an HTTP API at localhost:11434. If Ollama is not
running, the caller falls back to the BART pipeline.
"""
import re
import json
import logging
import urllib.request

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a professional compliance summarization assistant for a bank. "
    "You ALWAYS summarize the regulatory circular you are given, in the exact "
    "format requested. You never refuse, never add disclaimers or warnings, and "
    "never ask questions. Base the summary strictly and only on the circular's "
    "content."
)

_QA_SYSTEM_PROMPT = (
    "You are a helpful assistant that answers bank staff questions about "
    "regulatory circulars. Answer using ONLY the provided context. If the answer "
    "is not in the context, say you could not find it in the circulars. Be "
    "concise and accurate, never invent information, and never refuse."
)


class LLMSummarizer:
    def __init__(self, config=None):
        config = config or {}
        self.url = config.get("OLLAMA_URL", "http://localhost:11434").rstrip("/")
        self.model = config.get("OLLAMA_MODEL", "llama3.2:3b")
        # Optional lighter model for chat; defaults to the summary model.
        self.chat_model = config.get("OLLAMA_CHAT_MODEL") or self.model
        self.timeout = int(config.get("OLLAMA_TIMEOUT", 300))
        self.keep_alive = config.get("OLLAMA_KEEP_ALIVE", "30m")
        self.max_ctx = int(config.get("OLLAMA_MAX_CTX", 16384))
        ng = config.get("OLLAMA_NUM_GPU")
        self.num_gpu = int(ng) if ng not in (None, "") else None  # 0 => full CPU
        cng = config.get("OLLAMA_CHAT_NUM_GPU")
        # None => auto-place chat model; 0 => full CPU for chat.
        self.chat_num_gpu = int(cng) if cng not in (None, "") else None

    # ---- availability -------------------------------------------------
    def available(self) -> bool:
        """True if the Ollama service is reachable (quick check)."""
        try:
            with urllib.request.urlopen(f"{self.url}/api/tags", timeout=3) as r:
                return r.status == 200
        except Exception:  # noqa: BLE001 — service down / not installed
            return False

    # ---- summarisation ------------------------------------------------
    def summarize(self, text: str, target_words: int) -> str:
        """Return a structured summary string (Overview + Key Points)."""
        # Keep input within the model's context window (~16k tokens ≈ 12k words).
        words = text.split()
        if len(words) > 12000:
            words = words[:12000]
            text = " ".join(words)

        # Size the context to the document (+room for output) so small circulars
        # stay fast and large ones are still read in full. Capped by OLLAMA_MAX_CTX
        # (lower it on small-VRAM GPUs to keep more layers on the GPU).
        need = int(len(words) * 1.4) + 1800
        num_ctx = min(self.max_ctx, max(4096, need))
        # num_predict caps output tokens (the main CPU cost). ~900 ≈ 600 words max.
        content = self._chat(_SYSTEM_PROMPT, self._build_prompt(text, target_words),
                             num_ctx=num_ctx, num_predict=900)
        return self._normalise(content)

    # ---- RAG answer generation ----------------------------------------
    def answer(self, question: str, context: str) -> str:
        """Answer a question grounded ONLY in the retrieved circular context."""
        words = context.split()
        if len(words) > 6000:
            context = " ".join(words[:6000])
        num_ctx = min(self.max_ctx, max(2048, int(len(context.split()) * 1.4) + 1100))
        # chat_num_gpu: None auto-places the chat model; 0 forces full CPU (often
        # faster than a CPU/GPU split on weak GPUs). Independent of summaries.
        ans = self._chat(_QA_SYSTEM_PROMPT,
                         self._build_qa_prompt(question, context),
                         num_ctx=num_ctx, num_predict=900,
                         model=self.chat_model, num_gpu=self.chat_num_gpu).strip()
        ans = ans.replace("**", "")                       # drop markdown bold
        ans = re.sub(r"(?m)^\s*[*•]\s+", "- ", ans)       # normalise bullets
        return ans

    def refine_query(self, question: str) -> str:
        """Fix typos / split words into a clean retrieval query (keeps domain terms)."""
        prompt = (
            "Rewrite the question below into a clean search query for finding text "
            "in bank circulars. Fix spelling mistakes and join split words (e.g. "
            "'applicatio n' -> 'application'). Keep banking terms and abbreviations "
            "(AML, KYC, PFCA, SME, CRIB, etc.) unchanged. Return ONLY the rewritten "
            "query, nothing else.\n\n"
            f"Question: {question}\nSearch query:"
        )
        try:
            out = self._chat(
                "You rewrite user questions into clean search queries. Return only "
                "the query text.",
                prompt, num_ctx=1024, num_predict=40,
                model=self.chat_model, num_gpu=self.chat_num_gpu).strip()
        except Exception:  # noqa: BLE001
            return question
        out = (out.splitlines() or [""])[0].strip().strip('"').strip()
        # Guard against the model rambling or returning nothing usable.
        if not out or len(out.split()) > 25:
            return question
        return out

    def keywords(self, text: str, n: int = 5) -> list:
        """Extract the n most important key terms/topics from a summary."""
        prompt = (
            f"From the bank circular summary below, list the {n} most important key "
            "terms or topics (short noun phrases, 1-4 words each) that capture what "
            "the circular is about. Return ONLY a comma-separated list — no numbering, "
            "no explanations, no extra text.\n\n"
            f"SUMMARY:\n{text}"
        )
        out = self._chat(
            "You extract key terms. Return only a comma-separated list of terms.",
            prompt, num_ctx=2048, num_predict=80,
            model=self.chat_model, num_gpu=self.chat_num_gpu).strip()
        terms = []
        for part in re.split(r"[,\n]", out):
            p = re.sub(r"^\s*\d+[.)]\s*", "", part).strip().strip('"').strip("-•* ").strip()
            if p and 1 <= len(p.split()) <= 5 and re.search(r"[A-Za-z]", p):
                terms.append(p)
        return terms[:n]

    # ---- shared Ollama chat call --------------------------------------
    def _chat(self, system: str, user: str, num_ctx: int, num_predict: int,
              model: str = None, num_gpu="inherit") -> str:
        ng = self.num_gpu if num_gpu == "inherit" else num_gpu
        payload = {
            "model": model or self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "keep_alive": self.keep_alive,
            "options": {
                "temperature": 0.2,
                "top_p": 0.9,
                "num_ctx": num_ctx,
                "num_predict": num_predict,
            },
        }
        if ng is not None:      # 0 forces full CPU; None lets Ollama auto-place
            payload["options"]["num_gpu"] = ng
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.url}/api/chat", data=data,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            out = json.loads(resp.read().decode("utf-8"))
        return (out.get("message") or {}).get("content", "").strip()

    @staticmethod
    def _build_qa_prompt(question: str, context: str) -> str:
        return (
            "Answer the question using ONLY the context from bank circulars below.\n\n"
            f"CONTEXT:\n{context}\n\n"
            f"QUESTION: {question}\n\n"
            "Rules:\n"
            "- Use only the context. Answer with whatever relevant information the "
            "context contains, summarised in your own words. Only if there is NO "
            'relevant information at all, reply exactly: "I could not find that in the '
            'circulars."\n'
            "- Do NOT apologise and do NOT add notes about details you could not find "
            "(e.g. never write '(I could not find the specific details...)'). Just give "
            "the available information directly.\n"
            "- If the circular explains the answer in detail (conditions, requirements, "
            "standards, steps or sub-points), include those details using bullet points "
            "and keep exact figures, dates and defined terms. If only brief or partial "
            "information is available, give that briefly.\n"
            "- If the question is about a form, application form, annexure, checklist, "
            "template or attachment: list ALL the relevant forms/annexures the circular "
            "contains by name (e.g. 'Annexure II - Remote Work Application Form', "
            "'Annexure III - Remote Work Approval Checklist', 'Annexure IV - Remote Work "
            "Agreement'), then tell the user to download or preview the circular to "
            "access and fill them. Do NOT reproduce, quote, or list any of the form's "
            "fields, labels, blank lines or contents.\n"
            "- Do not mention the word context or that you were given passages.\n"
            "- Do not refuse and do not add disclaimers.\n\n"
            "Answer:"
        )

    @staticmethod
    def _build_prompt(text: str, target_words: int) -> str:
        return (
            "You are a banking compliance analyst. Read the regulatory circular "
            "below and write a CONCISE summary for bank staff.\n\n"
            'CIRCULAR TEXT:\n"""' + text + '"""\n\n'
            "Rules:\n"
            "- Use ONLY information stated in the circular. Do not add, assume, or invent anything.\n"
            "- Preserve exact figures, dates, deadlines, amounts and defined terms.\n"
            "- Do NOT invent or guess acronym meanings. If the circular defines an "
            "acronym, use ITS wording; otherwise keep the acronym as-is or use the "
            "correct standard banking meaning: LGD = Loss Given Default, PD = "
            "Probability of Default, EAD = Exposure at Default, ECL = Expected Credit "
            "Loss, NPL = Non-Performing Loan, SME = Small and Medium Enterprise, "
            "KYC = Know Your Customer, AML = Anti-Money Laundering, CBSL = Central "
            "Bank of Sri Lanka. Never expand LGD as 'Loan Loss Coverage'.\n"
            "- Focus on what people must DO: key obligations, procedures, eligibility, "
            "entitlements and deadlines. Do NOT list definitions or glossary terms.\n"
            "- Be CONCISE: give only the MOST important points. Consolidate related "
            "details into one bullet and OMIT minor procedural detail and long "
            "checklists (summarise them in a phrase instead of listing every item).\n"
            "- Do NOT repeat, quote, or paste the circular text back.\n"
            "- Be clear and grammatical.\n"
            f"- Keep the whole summary to about {target_words} words, with roughly "
            "6-10 key-point bullets (not more).\n\n"
            "Write ONLY the following two sections, and nothing after them:\n\n"
            "Overview:\n"
            "<2-3 sentence plain-English overview of what the circular is about>\n\n"
            "Key Points:\n"
            "- <a key requirement, action, eligibility rule, procedure or deadline>\n"
            "- <next most important point>"
        )

    @staticmethod
    def _normalise(resp: str) -> str:
        """Tidy output: strip fences and cut any echoed circular text after the summary."""
        resp = resp.strip()
        if resp.startswith("```"):
            resp = resp.strip("`").strip()
        # Drop any preamble before the Overview section (e.g. "Here is the summary:").
        m = re.search(r"Overview\s*:", resp, re.IGNORECASE)
        if m:
            resp = resp[m.start():].strip()
        # Cut anything the model appended after the summary (echoed source text).
        for marker in ("\nCircular:", "\nCIRCULAR", "\nCircular Text", '\n"""', "\nCircular text"):
            i = resp.find(marker)
            if i != -1:
                resp = resp[:i].strip()
        # Convert markdown bold section headers ("**Overview**") to "Overview:".
        resp = re.sub(r"(?im)^\s*\*\*\s*(Overview|Key Points?)\s*\*\*\s*:?\s*$",
                      lambda m: m.group(1).strip() + ":", resp)
        # Normalise bullet markers (*, •) to "-" so the UI renders them as a list.
        resp = re.sub(r"(?m)^\s*[*•]\s+", "- ", resp)
        # Drop any remaining markdown bold markers.
        resp = resp.replace("**", "")
        return resp
