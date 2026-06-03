import io
import re
import urllib.request

import pandas as pd

WIKI_SOURCES = [
    "https://en.wikipedia.org/wiki/List_of_best-selling_Nintendo_Switch_video_games",
    "https://en.wikipedia.org/wiki/List_of_best-selling_Nintendo_Switch_2_games",
    "https://en.wikipedia.org/wiki/List_of_best-selling_Wii_U_video_games",
    "https://en.wikipedia.org/wiki/List_of_best-selling_Wii_video_games",
    "https://en.wikipedia.org/wiki/List_of_best-selling_Nintendo_DS_video_games",
    "https://en.wikipedia.org/wiki/List_of_best-selling_Nintendo_3DS_video_games",
    "https://en.wikipedia.org/wiki/List_of_best-selling_GameCube_video_games",
    "https://en.wikipedia.org/wiki/List_of_best-selling_Game_Boy_Advance_video_games",
]

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; game-sales-elt/1.0)"}
_TITLE_COLS = {"Title", "Game"}
_SALES_COLS = {"Copies sold", "Sales"}
_AS_OF_COLS = {"As of"}
_ANNOTATION_RE = re.compile(r"(\[.*?\]|†)+$")

WIKI_HEADER = ["Game Title", "Sales", "system", "as of", "source"]

_SYSTEM_MAP = [
    ("Nintendo_Switch_2", "Nintendo Switch 2"),
    ("Nintendo_Switch", "Nintendo Switch"),
    ("Wii_U", "Wii U"),
    ("Wii", "Wii"),
    ("Nintendo_DS", "Nintendo DS"),
    ("Nintendo_3DS", "Nintendo 3DS"),
    ("GameCube", "GameCube"),
    ("Game_Boy_Advance", "Game Boy Advance"),
]


def _system_from_url(url: str) -> str:
    for fragment, system in _SYSTEM_MAP:
        if fragment in url:
            return system
    return "Unknown"


def _strip_annotations(col) -> str:
    if pd.isna(col):
        return ""
    return _ANNOTATION_RE.sub("", str(col)).strip()


def _fetch_html(url: str) -> str:
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req) as resp:
        return resp.read().decode("utf-8")


def _find_games_table(tables: list[pd.DataFrame]) -> pd.DataFrame:
    """Return the first table that has a sales column and a title column.

    Column names are matched after stripping footnote annotations like [4] or [a].
    """
    for table in tables:
        clean_cols = {_strip_annotations(c) for c in table.columns}
        if clean_cols & _SALES_COLS and clean_cols & _TITLE_COLS:
            table.columns = [_strip_annotations(c) for c in table.columns]
            table = table.apply(lambda s: s.map(_strip_annotations))
            return table
    raise ValueError(f"No table with a sales column {_SALES_COLS} and a title column {_TITLE_COLS} found on page")


def extract_sales_table(url: str) -> pd.DataFrame:
    html = _fetch_html(url)
    tables = pd.read_html(io.StringIO(html), flavor="lxml")
    return _find_games_table(tables)


def extract_all_tables() -> list[tuple[str, pd.DataFrame]]:
    """Fetch and return (url, DataFrame) for every entry in WIKI_SOURCES."""
    results = []
    for url in WIKI_SOURCES:
        df = extract_sales_table(url)
        results.append((url, df))
    return results


def extract_rows() -> list[list]:
    """Return all tables as a flat list of rows matching WIKI_HEADER."""
    rows = []
    for url, df in extract_all_tables():
        col_map = {c: "Game Title" for c in df.columns if c in _TITLE_COLS}
        col_map.update({c: "Sales" for c in df.columns if c in _SALES_COLS})
        as_of_col = next((c for c in df.columns if c in _AS_OF_COLS), None)
        if as_of_col:
            col_map[as_of_col] = "as of"
        df = df.rename(columns=col_map)
        keep = ["Game Title", "Sales"] + (["as of"] if as_of_col else [])
        df = df[keep].copy()
        if "as of" not in df.columns:
            df["as of"] = ""
        df["system"] = _system_from_url(url)
        df["source"] = url
        rows.extend(df[WIKI_HEADER].values.tolist())
    return rows


if __name__ == "__main__":
    rows = extract_rows()
    print(f"Extracted {len(rows)} rows")
