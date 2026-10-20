"""Split the raw OCR dump into one record per screenshot, verbatim."""
from __future__ import annotations

import re
from dataclasses import dataclass

HEADER_RE = re.compile(r"^=== SCREENSHOT: (?P<id>.+?) ===\s*$")


@dataclass(frozen=True)
class Line:
    no: int          # 1-based line number within the raw file (provenance)
    idx: int         # 0-based index within the record
    text: str        # exactly as in the file (trailing newline stripped)


@dataclass(frozen=True)
class Record:
    record_id: str
    header_line_no: int
    lines: tuple[Line, ...]

    @property
    def raw_text(self) -> str:
        return "\n".join(l.text for l in self.lines)


def split_records(raw: str) -> list[Record]:
    """Return records in file order. Text before the first header (none today) is ignored."""
    records: list[Record] = []
    cur_id: str | None = None
    cur_hdr = 0
    buf: list[Line] = []

    def flush():
        if cur_id is not None:
            # Drop trailing blank separator lines; keep interior blanks.
            while buf and not buf[-1].text.strip():
                buf.pop()
            records.append(Record(cur_id, cur_hdr, tuple(buf)))

    for no, text in enumerate(raw.splitlines(), start=1):
        m = HEADER_RE.match(text)
        if m:
            flush()
            cur_id, cur_hdr, buf = m.group("id"), no, []
            continue
        if cur_id is not None:
            buf.append(Line(no, len(buf), text))
    flush()
    return records
