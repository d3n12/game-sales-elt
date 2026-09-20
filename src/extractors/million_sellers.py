import logging
import re
import unicodedata
from datetime import datetime
from pathlib import Path
import pdfplumber

_logger = logging.getLogger(__name__)

PDF_DIR = Path(__file__).parent.parent.parent / "pdfs"

HEADINGS = {
    "Million-Seller Nintendo First-Party Titles",
    "Million-Seller Nintendo Titles",
    "Million-Seller Titles of NINTENDO Products",
}

FIXED_HEADER = ["Game Title", "Global", "Japan", "Outside of Japan", "Life-to-date Global", "system", "Fiscal Year", "as of", "source"]

_NUMBER_RE = re.compile(r"^[\d,]+$|^-$")
_PLATFORM_PREFIXES = [
    "Nintendo Switch 2", "Nintendo Switch", "Nintendo 3DS",
    "Wii U", "Nintendo DS", "Wii", "Game Boy Advance", "Nintendo GameCube",
]
_SECTION_HEADERS = {"Nintendo Switch 2", "Nintendo Switch"}


def get_newest_pdf(folder: Path) -> Path:
    pdfs = sorted(folder.glob("*.pdf"), key=lambda p: p.name, reverse=True)
    if not pdfs:
        raise FileNotFoundError(f"No PDF files found in {folder}")
    return pdfs[0]


def _expand_rows(table: list) -> list[list[str]]:
    """Split cells containing line breaks into separate table rows."""
    expanded = []
    for row in table:
        split_cells = [(cell or "").split("\n") for cell in row]
        max_lines = max(len(c) for c in split_cells)
        for i in range(max_lines):
            expanded.append([c[i].strip() if i < len(c) else "" for c in split_cells])
    return [row for row in expanded if any(cell for cell in row)]


def _merge_continuation_rows(rows: list[list[str]]) -> list[list[str]]:
    """Merge rows that are continuations of the previous row.

    Criterion: first cell empty/"-" and at most 2 non-empty cells → continuation.
    """
    result = []
    for row in rows:
        non_empty = [c for c in row if c and c != "-"]
        first_empty = not row[0] or row[0] == "-"
        all_others_empty = all(not c or c == "-" for c in row[1:])
        is_continuation = result and (
            (first_empty and len(non_empty) <= 2) or   # column header fragment
            (not first_empty and all_others_empty)     # multi-line game title
        )
        if is_continuation:
            prev = result[-1]
            merged = []
            for a, b in zip(prev, row):
                if b and b != "-":
                    sep = " " if (a and a != "-") else ""
                    merged.append(f"{a}{sep}{b}".strip())
                else:
                    merged.append(a)
            result[-1] = merged
        else:
            result.append(row)
    return result


def _parse_date_from_filename(path: Path) -> str:
    return datetime.strptime(path.stem[:6], "%y%m%d").strftime("%Y-%m-%d")


def _normalize_text(text: str) -> str:
    """Normalize full-width Unicode chars to ASCII and fix 4x-repetition font bug."""
    text = unicodedata.normalize("NFKC", text)
    return re.sub(r"(.)\1{3}", r"\1", text)


def _parse_fy(value: str) -> str:
    m = re.match(r"(FY\d+(?:/\d+)?)", value)
    return m.group(1) if m else value


def _looks_like_number(s: str) -> bool:
    return bool(_NUMBER_RE.match(s.strip())) if s else False


def _detect_platform(line: str) -> str | None:
    for p in _PLATFORM_PREFIXES:
        if line == p or line.startswith(p + " "):
            return p
    return None


def _parse_data_line(line: str) -> tuple[str, str, str, str, str] | None:
    """Parse 'Title N1 N2 N3 N4' - the last 4 tokens are always the sales figures."""
    parts = line.split()
    if len(parts) < 5:
        return None
    candidates = parts[-4:]
    title = " ".join(parts[:-4])
    if title and all(_looks_like_number(c) for c in candidates):
        return title, candidates[0], candidates[1], candidates[2], candidates[3]
    return None


def _is_old_format(raw_rows: list) -> bool:
    """Old PDFs have 4-column tables without game titles in the first column."""
    return bool(raw_rows) and len(raw_rows[0]) < 5


def _parse_rows_from_text(text: str, as_of: str, source: str) -> list[list[str]]:
    """Fallback for old PDFs: reads game titles and figures directly from page text."""
    current_system = "Nintendo Switch"
    current_fy = "-"

    fy_match = re.search(r"(FY\d+(?:/\d+)?)", text)
    if fy_match:
        current_fy = _parse_fy(fy_match.group(1))

    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parsed = _parse_data_line(line)
        if parsed:
            title, g, j, o, ltd = parsed
            rows.append([title, g, j, o, ltd, current_system, current_fy, as_of, source])
        else:
            platform = _detect_platform(line)
            if platform:
                current_system = platform
    return rows


def _add_system_column(rows: list[list[str]]) -> list[list[str]]:
    """Populate the 'system' column from the respective section header."""
    section_headers = {"Nintendo Switch 2", "Nintendo Switch"}
    result = []
    current_system = "-"
    current_fy = "-"
    for i, row in enumerate(rows):
        if row[0] in section_headers:
            current_system = row[0]
            current_fy = _parse_fy(row[1]) if len(row) > 1 and row[1] != "-" else current_fy
        elif row[0] in ("-", "") and len(row) > 1 and row[1].startswith("FY"):
            # older PDFs: section header without platform label → only Nintendo Switch available
            current_fy = _parse_fy(row[1])
            if current_system == "-":
                current_system = "Nintendo Switch"
        if i == 0:
            result.append(row + ["system", "Fiscal Year"])
        else:
            result.append(row + [current_system, current_fy])
    return result


def _fill_missing_title_cells(page, tables: list, page_tables: list) -> list:
    """Fix rows where pdfplumber couldn't detect the first-column cell boundary.

    Some PDFs omit the left border line for alternating rows, producing None for
    cell[0]. We reconstruct the missing bbox from the table's left edge and the
    adjacent cell, then crop the page to extract the title text directly.
    """
    for ti, pt in enumerate(page_tables):
        if ti >= len(tables):
            break
        table_left = pt.bbox[0]
        for ri, row in enumerate(pt.rows):
            if ri >= len(tables[ti]):
                break
            if row.cells[0] is not None:
                continue
            if len(row.cells) < 2 or row.cells[1] is None:
                continue
            # Only fix data rows - skip header rows (cell[1] is not a number)
            raw_cell1 = (tables[ti][ri][1] or "") if tables[ti][ri] else ""
            if not _looks_like_number(raw_cell1.strip()):
                continue
            x1 = row.cells[1][0]
            # Subtract a small left margin: the detected table edge can be
            # a fraction of a point to the right of the actual glyph origin,
            # which causes within_bbox to clip the first character.
            x0 = max(0, table_left - 2)
            bbox = (x0, row.bbox[1], x1, row.bbox[3])
            # x_tolerance=1: default of 3 merges narrow inter-word gaps (e.g.
            # "XenobladeChronicles"); 1 pt safely separates words (gap ~2 pt)
            # while keeping intra-glyph kerning (gap ~0 pt) together.
            text = page.within_bbox(bbox).extract_text(x_tolerance=1) or None
            if text:
                tables[ti][ri][0] = text
    return tables


def _is_header_row(row: list) -> bool:
    """True if a row looks like a table header: first cell empty, others non-numeric."""
    if not row:
        return False
    if row[0] and row[0] != "-":
        return False
    non_empty = [c for c in row[1:] if c and c != "-"]
    return bool(non_empty) and not any(_looks_like_number(c) for c in non_empty)


def _combine_page_tables(tables: list) -> list[list[str]]:
    """Combine multiple side-by-side tables from a single page into one row sequence."""
    col_count = len(tables[0][0]) if tables[0] else 0
    combined: list[list[str]] = []
    first = True
    for t in tables:
        if not t or len(t[0]) != col_count:
            continue
        expanded = _expand_rows(t)
        if not expanded:
            continue
        if first:
            combined.extend(expanded)
            first = False
        else:
            # Skip leading header rows from subsequent tables. Headers from
            # different tables can have minor punctuation differences, so we
            # detect them semantically (first cell empty, rest non-numeric)
            # rather than by exact equality.
            skip = 0
            while skip < len(expanded) and _is_header_row(expanded[skip]):
                skip += 1
            combined.extend(expanded[skip:])
    return combined


def _extract_data_rows(path: Path) -> list[list[str]]:
    """Return the data rows of the million-seller table from a single PDF."""
    as_of = _parse_date_from_filename(path)
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = _normalize_text(page.extract_text() or "")
            text_lower = text.lower()
            if not any(h.lower() in text_lower for h in HEADINGS):
                continue
            page_tables = page.find_tables()
            if not page_tables:
                continue
            tables = [pt.extract() for pt in page_tables]
            if _is_old_format(tables[0]):
                return _parse_rows_from_text(text, as_of, path.name)
            tables = _fill_missing_title_cells(page, tables, page_tables)
            rows = _combine_page_tables(tables)
            rows = _merge_continuation_rows(rows)
            rows = [[cell or "-" for cell in row] for row in rows]
            rows = _add_system_column(rows)
            rows = [row + [as_of, path.name] for row in rows[1:]]
            return [row for row in rows if row[0] not in _SECTION_HEADERS and row[0] != "-"]
    return []


def extract_all_pdfs(folder: Path, logger: logging.Logger | None = None) -> list[list[str]]:
    """Extract million-seller rows from all PDFs in folder. Returns a flat list of data rows."""
    log = logger or _logger
    pdfs = sorted(folder.glob("*.pdf"), key=lambda p: p.name)
    if not pdfs:
        raise FileNotFoundError(f"No PDF files found in {folder}")

    all_rows = []
    for path in pdfs:
        rows = _extract_data_rows(path)
        if rows:
            all_rows.extend(rows)
        else:
            log.info("No million-seller table found in %s", path.name)
        log.info("%s %s (%d rows)", "OK" if rows else "--", path.name, len(rows))

    return all_rows
