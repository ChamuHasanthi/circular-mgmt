"""Faithfulness spot-check worksheet generator.

Faithfulness (is every claim in the summary supported by the source, with no
hallucinated facts?) can't be judged automatically with confidence, so this
produces a MANUAL scoring worksheet: for ~10 circulars it writes the summary
next to key source excerpts, with a blank verdict line for you to fill in.

Scoring rubric (record per summary in the worksheet):
    Faithful      — every claim is supported by the source; no invented facts
    Minor issue   — mostly faithful; one vague/overreaching phrase
    Unfaithful    — contains a claim not in (or contradicting) the source

Run:
    python eval_faithfulness.py            > faithfulness_worksheet.txt
    python eval_faithfulness.py 10         # sample size
Then read the worksheet, write a verdict on each, and tally the results.
"""
import sys
import textwrap

from app import create_app
from app.models.circular import Circular, Summary


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    app = create_app()
    with app.app_context():
        pub = Circular.query.filter_by(status="published").all()
        rows = [(c, Summary.query.filter_by(circular_id=c.id).first())
                for c in pub]
        rows = [(c, s) for c, s in rows if s and (c.extracted_text or "").strip()]
        rows = rows[:n]

        print("FAITHFULNESS SPOT-CHECK WORKSHEET")
        print("Rubric: Faithful / Minor issue / Unfaithful\n")
        print("For each: read the summary, confirm every claim appears in the")
        print("source excerpt, then write a verdict on the VERDICT line.\n")
        print("=" * 74)

        for i, (c, s) in enumerate(rows, 1):
            src = " ".join((c.extracted_text or "").split())
            print(f"\n[{i}] Circular {c.circular_number}  (id {c.id})")
            print("-" * 74)
            print("SUMMARY:")
            print(textwrap.fill(s.summary_text or "", 74,
                                initial_indent="  ", subsequent_indent="  "))
            print("\nSOURCE (first ~900 chars):")
            print(textwrap.fill(src[:900], 74,
                                initial_indent="  ", subsequent_indent="  "))
            print("\nVERDICT: ____________________   NOTES: ______________________")
            print("=" * 74)

        print(f"\nTally: ___ Faithful  ___ Minor issue  ___ Unfaithful   "
              f"(out of {len(rows)})")


if __name__ == "__main__":
    main()
