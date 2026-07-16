"""Latency benchmark — wall-clock time per summarization and per chat answer.

Produces the "rough latency" numbers for the thesis evaluation chapter:
  * seconds per summarization (LLM summary of a full circular)
  * seconds per chat response  (RAG retrieve + grounded LLM answer)

Measured end-to-end on the target hardware (local Ollama, NVIDIA MX350 2 GB),
so the figures reflect the real user-perceived wait, not model FLOPs.

Run (Ollama must be up, circulars published):
    python eval_latency.py            # 6 summaries, 6 chats
    python eval_latency.py 10 8       # 10 summaries, 8 chats
"""
import sys
import time
import statistics as stats

from app import create_app
from app.models.circular import Circular
from app.ai import get_index, get_chatbot
from app.ai.pipeline import AIEngine

CHAT_QUESTIONS = [
    "What is the main objective of this circular?",
    "Which organizations must comply with these instructions?",
    "What is the deadline mentioned in the circular?",
    "What penalties apply for non-compliance?",
    "Which forms or annexures must be submitted?",
    "What reporting requirements does this circular impose?",
    "When does this circular take effect?",
    "What definitions does the circular provide?",
]


def _fmt(name, xs):
    if not xs:
        print(f"{name}: no samples"); return
    print(f"{name}: n={len(xs)}  mean={stats.mean(xs):.1f}s  "
          f"median={stats.median(xs):.1f}s  min={min(xs):.1f}s  max={max(xs):.1f}s")


def main():
    n_sum = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    n_chat = int(sys.argv[2]) if len(sys.argv) > 2 else 6

    app = create_app()
    with app.app_context():
        engine = AIEngine(app.config)
        index = get_index(app.config)
        if index.is_empty():
            index.build(Circular.query.filter_by(status="published").all())
        chatbot = get_chatbot(app.config)

        pub = [c for c in Circular.query.filter_by(status="published").all()
               if (c.extracted_text or "").strip()]
        print(f"Benchmarking on {len(pub)} circulars "
              f"({n_sum} summaries, {n_chat} chats)\n" + "=" * 60)

        # ---- Summarization latency ----
        sum_times = []
        for c in pub[:n_sum]:
            t0 = time.perf_counter()
            engine.summarize(c.extracted_text)
            dt = time.perf_counter() - t0
            sum_times.append(dt)
            print(f"  summarize {c.circular_number:<10} {dt:6.1f}s")

        # ---- Chat-response latency ----
        chat_times = []
        for i in range(n_chat):
            q = CHAT_QUESTIONS[i % len(CHAT_QUESTIONS)]
            t0 = time.perf_counter()
            chatbot.answer(q, top_k=8)
            dt = time.perf_counter() - t0
            chat_times.append(dt)
            print(f"  chat q{i + 1:<9} {dt:6.1f}s  ({q[:40]})")

        print("=" * 60)
        _fmt("Summarization (s/circular)", sum_times)
        _fmt("Chat response (s/answer)  ", chat_times)


if __name__ == "__main__":
    main()
