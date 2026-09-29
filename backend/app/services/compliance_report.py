"""Print-ready compliance report for the dashboard PDF export."""
from datetime import datetime
import fitz


TEAL = (0.055, 0.486, 0.482)
DARK = (0.075, 0.153, 0.184)
MUTED = (0.37, 0.45, 0.49)
PALE = (0.93, 0.97, 0.97)
LINE = (0.84, 0.89, 0.90)
WHITE = (1, 1, 1)
AMBER = (0.67, 0.39, 0.05)
RED = (0.71, 0.17, 0.17)

PAGE_W, PAGE_H = fitz.paper_size("a4")
LEFT = 42
RIGHT = PAGE_W - LEFT
CONTENT_W = RIGHT - LEFT
BOTTOM = PAGE_H - 48


def _safe(value):
    """Use characters supported by PDF's built-in Helvetica font."""
    return str(value if value is not None else "-").replace("\u2013", "-").replace("\u2014", "-").encode("latin-1", "replace").decode("latin-1")


def _text(page, x, y, value, size=9, color=DARK, bold=False):
    page.insert_text((x, y), _safe(value), fontsize=size,
                     fontname="hebo" if bold else "helv", color=color)


def _wrap(value, width, size=9, bold=False):
    font = "hebo" if bold else "helv"
    words = _safe(value).split()
    if not words:
        return ["-"]
    lines = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if fitz.get_text_length(candidate, fontname=font, fontsize=size) <= width:
            current = candidate
            continue
        if current:
            lines.append(current)
            current = ""
        # Split unusually long document numbers instead of clipping them.
        while fitz.get_text_length(word, fontname=font, fontsize=size) > width:
            cut = len(word) - 1
            while cut > 1 and fitz.get_text_length(word[:cut], fontname=font, fontsize=size) > width:
                cut -= 1
            lines.append(word[:cut])
            word = word[cut:]
        current = word
    if current:
        lines.append(current)
    return lines


class Report:
    def __init__(self, bank_name, generated_at):
        self.doc = fitz.open()
        self.bank_name = bank_name
        self.generated_at = generated_at
        self.page = None
        self.y = 0
        self.new_page()

    def new_page(self):
        self.page = self.doc.new_page(width=PAGE_W, height=PAGE_H)
        self.page.draw_rect(fitz.Rect(0, 0, PAGE_W, 96), color=TEAL, fill=TEAL)
        # Small bank mark, matching the application icon.
        x, y = LEFT + 2, 23
        self.page.draw_polyline([(x, y + 16), (x + 15, y + 5), (x + 30, y + 16)], color=WHITE, width=1.8)
        for offset in (4, 11, 18, 25):
            self.page.draw_line((x + offset, y + 21), (x + offset, y + 39), color=WHITE, width=1.5)
        self.page.draw_line((x, y + 20), (x + 30, y + 20), color=WHITE, width=1.8)
        self.page.draw_line((x, y + 40), (x + 30, y + 40), color=WHITE, width=1.8)
        for i, line in enumerate(_wrap(self.bank_name.upper(), CONTENT_W - 55, 11, True)[:2]):
            _text(self.page, LEFT + 47, 38 + i * 13, line, 11, WHITE, True)
        _text(self.page, LEFT + 47, 71, "CIRCULAR COMPLIANCE REPORT", 15, WHITE, True)
        self.y = 115

    def ensure(self, height):
        if self.y + height > BOTTOM:
            self.new_page()

    def section(self, title, detail=None):
        self.ensure(43)
        self.y += 13
        _text(self.page, LEFT, self.y, title.upper(), 11, TEAL, True)
        self.page.draw_line((LEFT, self.y + 7), (RIGHT, self.y + 7), color=LINE, width=0.7)
        self.y += 20
        if detail:
            for line in _wrap(detail, CONTENT_W, 8):
                _text(self.page, LEFT, self.y, line, 8, MUTED)
                self.y += 11
        self.y += 5

    def paragraph(self, value):
        lines = _wrap(value, CONTENT_W, 9)
        self.ensure(len(lines) * 13 + 7)
        for line in lines:
            _text(self.page, LEFT, self.y + 10, line, 9)
            self.y += 13
        self.y += 7

    def metrics(self, values):
        width = (CONTENT_W - 18) / 3
        for row in range(2):
            self.ensure(69)
            for col in range(3):
                label, value, accent = values[row * 3 + col]
                x = LEFT + col * (width + 9)
                self.page.draw_rect(fitz.Rect(x, self.y, x + width, self.y + 58),
                                    color=LINE, fill=PALE, width=0.6)
                _text(self.page, x + 11, self.y + 19, label.upper(), 7.5, MUTED, True)
                _text(self.page, x + 11, self.y + 43, value, 17, accent, True)
            self.y += 67

    def table(self, headers, widths, records):
        assert sum(widths) <= CONTENT_W + 0.1

        def header():
            self.ensure(55)
            self.page.draw_rect(fitz.Rect(LEFT, self.y, RIGHT, self.y + 26),
                                color=TEAL, fill=TEAL)
            x = LEFT
            for label, width in zip(headers, widths):
                _text(self.page, x + 7, self.y + 17, label, 7.3, WHITE, True)
                x += width
            self.y += 26

        header()
        if not records:
            records = [("No data available",) + ("",) * (len(headers) - 1)]
        for index, row in enumerate(records):
            cells = [_wrap(value, width - 14, 8) for value, width in zip(row, widths)]
            height = max(24, 8 + max(len(cell) for cell in cells) * 11)
            if self.y + height > BOTTOM:
                self.new_page()
                header()
            if index % 2 == 0:
                self.page.draw_rect(fitz.Rect(LEFT, self.y, RIGHT, self.y + height),
                                    color=PALE, fill=PALE)
            x = LEFT
            for lines, width in zip(cells, widths):
                for line_index, line in enumerate(lines):
                    _text(self.page, x + 7, self.y + 17 + line_index * 11, line, 8)
                x += width
            self.page.draw_line((LEFT, self.y + height), (RIGHT, self.y + height), color=LINE, width=0.4)
            self.y += height
        self.y += 9

    def circulars(self, rows):
        if not rows:
            self.paragraph("No published circulars are available for this report.")
            return
        for item in rows:
            number = _wrap(item["number"], 170, 9, True)
            title = _wrap(item["title"], CONTENT_W - 24, 9)
            details = (
                f"Priority: {item['priority']}    Due: {item['deadline']}    "
                f"Recipients: {item['total']}    Acknowledged: {item['acknowledged']}    "
                f"Pending: {item['pending']}    Late: {item['overdue']}    Rate: {item['rate']}%"
            )
            detail_lines = _wrap(details, CONTENT_W - 24, 7.8)
            height = 13 * len(number) + 12 * len(title) + 31 + 10 * len(detail_lines)
            self.ensure(height + 6)
            top = self.y
            self.page.draw_rect(fitz.Rect(LEFT, top, RIGHT, top + height), color=LINE, width=0.7)
            self.page.draw_rect(fitz.Rect(LEFT, top, LEFT + 4, top + height), color=TEAL, fill=TEAL)
            cursor = top + 18
            for line in number:
                _text(self.page, LEFT + 12, cursor, line, 9, TEAL, True)
                cursor += 13
            for line in title:
                _text(self.page, LEFT + 12, cursor + 2, line, 9, DARK)
                cursor += 12
            cursor += 12
            for line in detail_lines:
                _text(self.page, LEFT + 12, cursor, line, 7.8, MUTED)
                cursor += 10
            self.y = top + height + 8

    def finish(self):
        for index, page in enumerate(self.doc, 1):
            page.draw_line((LEFT, PAGE_H - 37), (RIGHT, PAGE_H - 37), color=LINE, width=0.7)
            _text(page, LEFT, PAGE_H - 23,
                  f"{self.bank_name}  |  Generated {self.generated_at:%Y-%m-%d %H:%M} UTC",
                  7.5, MUTED)
            _text(page, RIGHT - 64, PAGE_H - 23,
                  f"Page {index} of {self.doc.page_count}", 7.5, MUTED)
        data = self.doc.tobytes(garbage=4, deflate=True)
        self.doc.close()
        return data


def build_compliance_pdf(data, bank_name="Bank Compliance Office", generated_at=None):
    """Render a complete dashboard snapshot to PDF bytes."""
    generated_at = generated_at or datetime.utcnow()
    report = Report(bank_name, generated_at)
    report.paragraph(
        "Management overview of published circulars, recipient acknowledgements, "
        "department performance and supporting operational measures."
    )

    summary = data["summary"]
    report.section("Executive summary")
    report.metrics([
        ("Published circulars", summary["published"], TEAL),
        ("Recipients", summary["recipients"], DARK),
        ("Acknowledged", summary["acknowledged"], TEAL),
        ("Pending", summary["pending"], AMBER),
        ("Flagged late", summary["overdue"], RED),
        ("Acknowledgement rate", f"{summary['rate']}%", TEAL),
    ])
    report.paragraph(
        f"Status detail: {summary['unread']} unread; {summary['read']} read; "
        f"{summary['acknowledged']} acknowledged. Rates use assigned recipient records as the denominator."
    )

    report.ensure(110)
    report.section("Compliance by department", "Recipient acknowledgement records grouped by current user department.")
    report.table(
        ["Department", "Recipients", "Ack.", "Pending", "Late", "Rate"],
        [196, 65, 55, 65, 50, 80],
        [(d["name"], d["total"], d["acknowledged"], d["pending"], d["overdue"], f"{d['rate']}%")
         for d in data["departments"]],
    )

    report.ensure(120)
    report.section("Circular compliance", "Published circulars, newest first. Late is the stored late flag on recipient records.")
    report.circulars(data["circulars"])

    report.ensure(110)
    report.section("Category distribution", "Number of published circulars assigned to each category; a circular may have several categories.")
    report.table(["Category", "Circulars"], [400, 111], data["categories"])

    report.ensure(225)
    report.section("Operational context")
    users = data["users"]
    ai = data["ai"]
    report.table(["Measure", "Value"], [330, 181], [
        ("Users - total / active / inactive", f"{users['total']} / {users['active']} / {users['inactive']}"),
        ("Summaries generated", ai["summaries"]),
        ("Average summary processing time", f"{ai['avg_seconds']} seconds" if ai["avg_seconds"] is not None else "Not available"),
        ("Average ROUGE score", ai["avg_rouge"] if ai["avg_rouge"] is not None else "Not available"),
        ("Summary models used", ", ".join(ai["models"]) or "Not available"),
    ])
    report.table(["User role", "Users"], [400, 111], data["roles"])
    report.table(["User department", "Users"], [400, 111], data["user_departments"])
    report.paragraph("This report is a snapshot at the generation time shown in the footer. Blank or unavailable metrics are not estimated.")
    return report.finish()
