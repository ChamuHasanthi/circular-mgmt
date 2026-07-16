"""RAG evaluation harness — measure retrieval + answer accuracy.

Runs a set of question/expected-answer pairs through the chatbot and reports:
  * Retrieval hit-rate — did the expected source circular appear in the citations?
  * Answer accuracy    — did the answer contain the expected keyword(s)?

Use it to compare the chatbot before/after changes (e.g. hybrid retrieval, QA
reader) with an objective number for the thesis evaluation chapter.

Setup:
  1. Ensure MySQL is running and circulars are published.
  2. Edit eval_questions.json (see the template created on first run).
  3. Run:  python eval_rag.py

Each eval item: {"question": ..., "expected_circular": "02/2024",
                 "expected_keywords": ["14 days", "enhanced due diligence"]}
`expected_circular` and `expected_keywords` are both optional.
"""
import json
import os
import re

from app import create_app
from app.extensions import db
from app.models.circular import Circular
from app.ai import get_index, get_chatbot

EVAL_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "eval_questions.json")

_TEMPLATE = [
    {
        "question": "What is the deadline to acknowledge this circular?",
        "expected_circular": "",
        "expected_keywords": ["days"],
    }
]


_STOP = {"the", "a", "an", "of", "to", "and", "or", "in", "on", "for", "is",
         "be", "must", "this", "that", "by", "with", "as", "at", "all"}


def _stem(word):
    """Crude suffix stripper so suspend/suspended/suspension all share a root."""
    for suf in ("ations", "ation", "ing", "ed", "es", "s", "ion"):
        if word.endswith(suf) and len(word) - len(suf) >= 4:
            return word[: -len(suf)]
    return word


def _kw_hit(keyword, answer):
    """A keyword counts as found if either the phrase appears verbatim, or all
    of its significant (non-stopword) words appear stem-matched in the answer.

    This tolerates wording differences the exact-substring test rejected:
      'suspension' vs 'suspended', 'licensed commercial banks' vs 'licensed
    banks'. It avoids false hits by requiring EVERY content word to match.
    """
    kl, al = keyword.lower().strip(), answer.lower()
    if kl in al:
        return True
    ans_stems = {_stem(w) for w in re.findall(r"[a-z0-9]+", al)}
    kw_words = [w for w in re.findall(r"[a-z0-9]+", kl) if w not in _STOP]
    if not kw_words:
        return kl in al
    return all(_stem(w) in ans_stems for w in kw_words)


def load_eval():
    if not os.path.exists(EVAL_FILE):
        with open(EVAL_FILE, "w", encoding="utf-8") as fh:
            json.dump(_TEMPLATE, fh, indent=2)
        print(f"Created a template eval set at {EVAL_FILE}. Fill it in and re-run.")
        return []
    with open(EVAL_FILE, "r", encoding="utf-8") as fh:
        return json.load(fh)


def main():
    app = create_app()
    with app.app_context():
        items = load_eval()
        if not items:
            return

        index = get_index(app.config)
        if index.is_empty():
            index.build(Circular.query.filter_by(status="published").all())
        chatbot = get_chatbot(app.config)

        # Map circular number -> id so questions can be answered SCOPED to their
        # circular (the realistic mode for "this circular" questions).
        num_to_id = {c.circular_number: c.id for c in Circular.query.all()}

        retr_hits = ans_hits = retr_total = ans_total = 0
        print(f"\nEvaluating {len(items)} questions\n" + "=" * 60)
        for it in items:
            q = it["question"]
            exp_c = (it.get("expected_circular") or "").strip()
            cid = num_to_id.get(exp_c)
            if exp_c and cid is None:
                print(f"[skip] '{exp_c}' not in database."); continue

            # --- Retrieval hit-rate (GLOBAL): can the system locate the right
            #     circular from the question alone? (fast — no generation) ---
            if exp_c:
                retr_total += 1
                found = {r["circular_number"] for r in index.search(q, top_k=8)}
                retr_hits += exp_c in found

            # --- Answer accuracy (SCOPED to the expected circular) ---
            res = chatbot.answer(q, top_k=8, circular_id=cid)
            ans = res["answer"]
            line = f"\nQ: {q}\nA: {ans[:180]}"

            kws = it.get("expected_keywords") or []
            if kws:
                ans_total += 1
                ok = any(_kw_hit(k, ans) for k in kws)
                ans_hits += ok
                line += f"\n   answer: {'HIT' if ok else 'MISS'} (expected one of {kws})"
            print(line)

        print("\n" + "=" * 60)
        if retr_total:
            print(f"Global retrieval hit-rate: {retr_hits}/{retr_total} "
                  f"= {retr_hits / retr_total:.0%}  (finds the right circular)")
        if ans_total:
            print(f"Scoped answer accuracy:    {ans_hits}/{ans_total} "
                  f"= {ans_hits / ans_total:.0%}  (answers from the right circular)")
        db.session.remove()


if __name__ == "__main__":
    main()
