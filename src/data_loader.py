"""
data_loader.py — Multi-table registry with parquet caching and auto schema generation.

TABLE_REGISTRY defines every table per module.
Same-period files are concatenated into one DataFrame.
Schema is auto-generated from the actual data — no manual column documentation needed.
"""
import pandas as pd
from pathlib import Path

DATA_DIR  = Path(__file__).parent.parent / "data"
CACHE_DIR = DATA_DIR / "cache"
CACHE_DIR.mkdir(exist_ok=True)

# ── Table registry ─────────────────────────────────────────────────────────────
# Each entry: list of (relative_path, format) tuples — combined into one DataFrame.
TABLE_REGISTRY: dict[str, dict[str, list[tuple[str, str]]]] = {
    "npl": {
        "outstanding": [
            ("test3 NPL/NPL Outstanding032026.csv",  "csv"),
            ("test3 NPL/NPL OutstandingQ42025.csv",  "csv"),
        ],
        "outstandingcol": [
            ("test3 NPL/NPL Outstandingcol032026.csv", "csv"),
            ("test3 NPL/NPL OutstandingcolQ42025.csv", "csv"),
        ],
        "collection": [
            ("test3 NPL/ผลเรียกเก็บNPL032026.xlsx",  "xlsx"),
            ("test3 NPL/ผลเรียกเก็บNPLQ42025.xlsx",   "xlsx"),
        ],
    },
    "npa": {
        "outstanding": [
            ("test3 NPA/NPA Outstanding032026.xlsx",    "xlsx"),
            ("test3 NPA/NPA Outstandingq42025.xlsx",    "xlsx"),
        ],
        "collection": [
            ("test3 NPA/ผลเรียกเก็บ NPA 032026.xlsx", "xlsx"),
            ("test3 NPA/ผลเรียกเก็บNPAQ42025.xlsx",    "xlsx"),
        ],
    },
}

# ── Display names for UI ───────────────────────────────────────────────────────
TABLE_LABELS: dict[str, str] = {
    "outstanding":    "Outstanding (Balance)",
    "outstandingcol": "Outstanding (Collateral View)",
    "collection":     "Collection Results",
}

# ── In-memory DataFrame cache ──────────────────────────────────────────────────
_df_cache: dict[str, pd.DataFrame] = {}


def get_modules() -> list[str]:
    return list(TABLE_REGISTRY.keys())


def get_tables(module: str) -> list[str]:
    return list(TABLE_REGISTRY.get(module, {}).keys())


def _cache_path(module: str, table: str) -> Path:
    return CACHE_DIR / f"{module}_{table}.parquet"


def _load_file(path: Path, fmt: str) -> pd.DataFrame:
    # Two-pass: peek headers first so we can force ID cols to str BEFORE pandas infers int.
    # Doing it after the fact (int → str) loses the leading zeros permanently.
    if fmt == "csv":
        peek = pd.read_csv(path, encoding="utf-8-sig", nrows=0)
        id_dtype = {c: str for c in peek.columns if "รหัส" in c or c.lower() in ("id", "code")}
        df = pd.read_csv(path, encoding="utf-8-sig", low_memory=False, dtype=id_dtype)
    else:
        peek = pd.read_excel(path, nrows=0)
        id_dtype = {c: str for c in peek.columns if "รหัส" in c or c.lower() in ("id", "code")}
        df = pd.read_excel(path, dtype=id_dtype)
    # Strip whitespace; also remove trailing .0 from Excel numeric-stored cells (15.0 → 15)
    for col in id_dtype:
        if col in df.columns:
            df[col] = df[col].where(
                df[col].isna(),
                df[col].astype(str).str.replace(r"\.0$", "", regex=True).str.strip(),
            )
    return df


def load_table(module: str, table: str) -> pd.DataFrame:
    """Load a table by module + table name.
    First call: reads source files, concatenates, saves parquet cache.
    Subsequent calls: loads from parquet (fast)."""
    key = f"{module}/{table}"
    if key in _df_cache:
        return _df_cache[key]

    cache = _cache_path(module, table)
    if cache.exists():
        df = pd.read_parquet(cache)
        _df_cache[key] = df
        return df

    entries = TABLE_REGISTRY.get(module, {}).get(table)
    if not entries:
        raise ValueError(f"Unknown table: module={module} table={table}")

    parts = []
    for rel_path, fmt in entries:
        full_path = DATA_DIR / rel_path
        print(f"Loading {full_path.name}...")
        parts.append(_load_file(full_path, fmt))

    df = pd.concat(parts, ignore_index=True)
    # Drop Grand Total / subtotal rows that Excel adds — these have non-numeric ปี values
    # and corrupt the column dtype from int to str, breaking all period filters.
    if 'ปี' in df.columns:
        valid_mask = pd.to_numeric(df['ปี'], errors='coerce').notna()
        dropped = (~valid_mask).sum()
        if dropped:
            print(f"  Dropping {dropped} non-data row(s) (Grand Total / subtotals)")
        df = df[valid_mask].copy()
        df['ปี'] = pd.to_numeric(df['ปี']).astype(int)
    # Coerce mixed-type object columns to string so pyarrow can write parquet
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].where(df[col].isna(), df[col].astype(str))
    df.to_parquet(cache, index=False)
    print(f"Cached: {cache.name}  ({len(df):,} rows)")

    _df_cache[key] = df
    return df


# ── Auto schema generation ─────────────────────────────────────────────────────
_CATEGORICAL_THRESHOLD = 30   # columns with fewer unique values get full value list


def get_schema_description(df: pd.DataFrame, module: str = "", table: str = "") -> str:
    """Auto-generate a schema string from any DataFrame.
    Categorical columns (< threshold unique values) show the full value list so the
    LLM knows exact filter values without any manual documentation."""

    header = f"Module: {module.upper()}  |  Table: {table}  |  {len(df):,} rows × {len(df.columns)} columns"
    lines = [header, "Currency: Thai Baht (฿) — values in full Baht, do not scale.", ""]
    lines.append("Columns (use EXACT Thai names in pandas code):")

    for col in df.columns:
        series  = df[col]
        dtype   = series.dtype
        n_null  = int(series.isna().sum())
        null_tag = f"  ⚠ {n_null:,} nulls" if n_null else ""

        if pd.api.types.is_numeric_dtype(dtype):
            non_null = series.dropna()
            if len(non_null):
                mn, mx, avg = non_null.min(), non_null.max(), non_null.mean()
                detail = f"numeric | {mn:,.2f} → {mx:,.2f}  mean={avg:,.2f}{null_tag}"
            else:
                detail = f"numeric | all null"

        elif pd.api.types.is_datetime64_any_dtype(dtype):
            detail = f"date | {series.min()} → {series.max()}{null_tag}"

        else:  # object / string
            n_unique = series.nunique(dropna=True)
            if n_unique <= _CATEGORICAL_THRESHOLD:
                vals = sorted(series.dropna().unique().tolist(), key=str)
                detail = f"categorical — EXACT values: {vals}{null_tag}"
            else:
                samples = series.dropna().head(3).tolist()
                detail = f"text | {n_unique:,} unique | samples: {samples}{null_tag}"

        lines.append(f"  '{col}': {detail}")

    lines += ["", "Sample rows (2):", df.head(2).to_string(index=False)]
    return "\n".join(lines)
