# NS-008 — System Documentation
**Natural Stupidity 008 | Architecture 3.0**
BAM Portfolio Chatbot — NPL / NPA Thai-language analytics assistant

---

## 1. Overview

NS-008 is a Thai-language chatbot for querying and analyzing BAM's NPL and NPA portfolio data. It combines deterministic routing, LLM agent orchestration, specialist code generation, and hybrid RAG retrieval to answer questions in natural Thai over pandas DataFrames loaded from CSV/Excel source files.

**Design goal:** test01 (fixed pipeline) was accurate but rigid. NS-007 (pure agent) was flexible but unfocused. NS-008 merges both: deterministic pre-routing for domain knowledge + agent orchestration for flexibility + specialist codegen for accuracy.

---

## 2. Architecture Overview

```
User Question
  │
  ├─ Load data tables (pandas DataFrames, parquet cached)
  ├─ RAG Retrieval (ChromaDB + Gemini Embedding 2)
  ├─ Classify (Groq llama-3.1-8b)
  │
  └─ Query Type?
       ├─ out_of_scope   → Reject (Thai message)
       ├─ clarification  → Ask clarifying question (stream)
       ├─ analytical     → Stream analysis (Typhoon)
       ├─ mixed          → Analyze criteria → Agent Loop → Summarize
       └─ data_query     → Pre-route → Follow-up detect → Agent Loop → Session update → Chart → Summarize
```

---

## 3. Pipeline — Step by Step

### Step 0: Data Loading
All tables for the active module are loaded at the start of every `run_query()` call. After the first call, data lives in the in-memory `_df_cache` dict and as parquet files on disk — source files are never re-read within the same process.

### Step 1: RAG Retrieval
`rag_retriever.py` runs a hybrid keyword + vector search over two ChromaDB collections:
- `global_gemini2` — business rules, risk framework (shared across modules)
- `{module}_gemini2` — column definitions, query examples for the active module

Result is passed to both the classifier (as context) and the agent (as initial RAG context).

### Step 2: Classify
`_classify()` calls Groq llama-3.1-8b (hardcoded — fast and cheap). Returns one of 5 types:

| Type | When |
|---|---|
| `out_of_scope` | Not about NPL/NPA portfolio |
| `clarification` | Bare "show/view" with no subject (Rule 0) |
| `analytical` | Reasoning/explanation — no data pull needed |
| `mixed` | Analytical criteria + real data pull needed |
| `data_query` | Direct data question needing code execution |

Report requests (`is_report=True`) always override to `data_query` unless `out_of_scope`.

### Step 3: Pre-route (data_query / mixed)
Deterministic domain rules in `_pre_route()` map Thai keywords to tables without any LLM call:
- Keywords like "ผลเรียกเก็บ", "cash", "lgo1" → `collection`
- Keywords like "หลักประกัน", "โฉนด", "ไร่" → `outstandingcol`
- TDR / ประนอมหนี้ → `outstanding`
- NPL_FORCE_COL list → `outstandingcol` (forced regardless of other signals)

If `_pre_route()` returns `None`, `_route_table()` calls the active LLM as a fallback.

### Step 4: Follow-up Detection
Runs only when `session["last_debtor_ids"]` is populated (i.e., a previous data result exists).

`_classify_followup(question, prev_question)` — LLM call returning `"followup"` or `"new"`.

If follow-up is confirmed, `_build_followup_context()` builds a hint string including:
- Count of previous IDs
- Which ID column to use (`รหัสลูกหนี้` for NPL, `รหัสตลาด` for NPA)
- A pandas filter expression using `_latest` variants

### Step 4.5: Report Export Short-Circuit
Before launching the agent, if all three conditions are true:
1. `is_report=True` (user asked for download/export)
2. `_is_followup=True`
3. `session["last_raw_result"]` is a non-empty DataFrame

→ Skip the agent entirely. Call `_save_report(session["last_raw_result"])` directly and return the Excel download. This exports exactly what the user already sees without re-querying.

### Step 5: Agent Loop
`_run_agent_loop()` runs an orchestrator LLM (user-selected model) with 3 tools:

| Tool | Limit | Purpose |
|---|---|---|
| `retrieve_knowledge` | ≤ 2× | Pull domain rules/column info from RAG |
| `generate_and_run` | ≤ 4× | Describe intent → specialist writes + runs code |
| `finish` | 1× | Signal result is ready |

The agent writes intent in plain English. A **separate specialist codegen LLM** (also user-selected) receives the full schema + code rules and writes the actual pandas code.

On error, `last_error_hint` is passed back to the specialist for self-correction on retry.

### Step 6: Specialist Codegen + Execute
`_generate_code()` calls the codegen LLM with:
- Full table schema (auto-generated from actual data)
- Code rules (PERIOD SCOPE, month format, ID column, follow-up filter)
- Agent's intent (plain English)
- Original user question (ground truth, separate from agent intent)
- `is_report` flag (enables REPORT MODE instructions)
- `error_hint` on retry

`_safe_exec()` runs the generated code in a restricted sandbox. Pre-filtered DataFrames are injected at exec time:

| Variable | Content |
|---|---|
| `df` | Primary table (outstanding or collection) — all periods |
| `df_col` | outstandingcol — all periods (NPL only) |
| `df_coll` | collection — all periods |
| `df_latest` | `df` filtered to latest year + latest month |
| `df_col_latest` | `df_col` filtered to latest period |
| `df_coll_latest` | `df_coll` filtered to latest period |
| `_prev_ids` | Set of IDs from previous query (follow-up only) |
| `df_user` | Uploaded Excel/CSV account list (if provided) |

**PERIOD SCOPE rule (3 cases):**
1. Default / "ล่าสุด" → use `df_latest` / `df_col_latest` / `df_coll_latest`
2. Trend / YoY / all periods → use `df` / `df_col` / `df_coll`
3. Explicit period named (e.g., "ธันวาคม") → use `df` / `df_col` / `df_coll` + manual filter

### Step 7: Session Update
`_update_session()` stores in thread-local session after every successful data query:
- `last_debtor_ids` — set of ID strings from the result (used by follow-up classifier)
- `last_table` — table name used (used by display-followup detection)
- `last_raw_result` — full result DataFrame (used by report export short-circuit)
- `last_report_file` — path if Excel was saved this turn

### Step 8: Try Chart
`_try_make_chart()` auto-generates a Plotly dark-mode bar chart when the result is:
- A `pd.Series` with 2–50 rows, or
- A 2-column `pd.DataFrame` with a numeric second column and 2–50 rows

Returns CDN-embedded HTML. Empty string if not applicable.

### Step 9: Summarize
`_summarize_stream()` calls Typhoon v2.5-30b (hardcoded — Thai-specialized) to produce a Thai-language narrative analysis of the result. Falls back to the user-selected provider if the Typhoon key is unavailable.

The summary system prompt includes a rule to end with one short line stating the temporal scope of the data in natural Thai (e.g., `ข้อมูล ณ เดือนมีนาคม 2569`). This replaced the static period badge system.

---

## 4. Query Types — Detail

### out_of_scope
Immediate rejection with a fixed Thai message. No LLM call beyond classify.

### clarification
Triggered when the question is a bare "show/view" with no subject (Rule 0 in classifier): e.g., "ขอดูหน่อย", "ขอดูตาราง". `_clarify_stream()` asks the user to specify what they want to see, listing available tables in Thai with descriptions.

### analytical
No agent, no code. `_analyze_stream()` receives all table schemas and streams a Thai reasoning/explanation response directly. Used for questions like "ทำไม NPL ถึงสูง" or "TDR คืออะไร" or "มีตารางอะไรบ้าง".

### mixed
Two-phase:
1. `_analyze_stream()` first — reasons about criteria and approach, streamed to user immediately.
2. Agent loop — analyst's output becomes the query plan. Agent executes a real data pull against the criteria.

Useful for questions like "ลูกหนี้ที่มีความเสี่ยงสูงที่สุด" where criteria must be reasoned first.

### data_query
Full pipeline: pre-route → follow-up detect → (short-circuit if report export) → agent → codegen → execute → session update → chart → summarize.

---

## 5. Data Layer

### Modules and Tables
```
npl:
  outstanding     — NPL debtor balance (CSV, utf-8-sig)
  outstandingcol  — NPL collateral per debtor (CSV, utf-8-sig)
  collection      — NPL collection results (Excel)

npa:
  outstanding     — NPA asset balance (Excel)
  collection      — NPA collection results (Excel)
```

### Data Periods
Two periods concatenated in each table:
- Q4 2025 — `ปี=2025`, `เดือน='December'` (collection) or `'Dec'` (outstanding/outstandingcol)
- Q1 2026 — `ปี=2026`, `เดือน='March'` (collection) or `'Mar'` (outstanding/outstandingcol)

**Month format difference (critical):**
- `collection` table: full English month name — `'December'`, `'March'`
- `outstanding` / `outstandingcol`: abbreviated — `'Dec'`, `'Mar'`
- Wrong format returns 0 rows silently. Codegen must use the correct format per table.

### Loading Pipeline
1. Source file → `_load_file()` — two-pass read: peek headers first, force รหัส-containing columns to `str` dtype to preserve leading zeros.
2. Files for the same table are concatenated with `pd.concat()`.
3. Grand Total / subtotal rows are dropped: rows where `pd.to_numeric(df['ปี'], errors='coerce')` is NaN.
4. Mixed-type object columns are coerced to string for pyarrow compatibility.
5. Saved as parquet in `data/cache/{module}_{table}.parquet`.
6. Subsequent loads read from parquet (fast) or in-memory dict (fastest).

### Auto Schema Generation
`get_schema_description()` inspects the actual DataFrame and generates a schema string:
- Numeric columns: min / max / mean
- Categorical columns (< 30 unique values): full value list (exact filter values for the LLM)
- Text columns: unique count + 3 samples
- Null counts flagged with ⚠

No manual column documentation is needed — the schema is always up to date with the actual data.

### Exec Scope Variables
```python
df        = primary table (outstanding or collection for NPA)
df_col    = outstandingcol (NPL only)
df_coll   = collection
df_latest      = df  filtered to latest ปี + latest เดือน
df_col_latest  = df_col filtered to latest ปี + latest เดือน
df_coll_latest = df_coll filtered to latest ปี + latest เดือน
_prev_ids = set of ID strings from previous query (follow-up only)
df_user   = uploaded account list DataFrame (if provided)
```

---

## 6. Session State

Thread-local (`threading.local`) — isolated per user session in a multi-user Gradio deployment.

```python
{
    "last_debtor_ids":  set[str] | None,   # IDs from last result — drives follow-up detection
    "last_table":       str | None,         # table used last turn — drives display-followup shortcut
    "last_module":      str | None,
    "last_report_file": str | None,         # path to last saved Excel report
    "last_report_rows": int,
    "last_report_cols": int,
    "last_raw_result":  pd.DataFrame | None, # full result — used by report export short-circuit
}
```

Session is reset at process restart. No persistence across server restarts (by design — data is sensitive).

---

## 7. Report Export

### Detection
`_is_report_request(question)` checks against `_REPORT_KEYWORDS`:
```python
["รายงาน", "ส่งออก", "ดาวน์โหลด", "ออกรายงาน", "ออกไฟล์", "สร้างรายงาน",
 "โหลด", "โหลดได้", "ขอโหลด", "บันทึก", "save", "ไฟล์",
 "export", "download", "report", "excel", "xlsx"]
```

### Short-circuit (follow-up export)
When `is_report=True` AND `_is_followup=True` AND `last_raw_result` is a non-empty DataFrame:
- Skip the agent entirely
- Export `last_raw_result` directly as Excel
- Yields `(final_text, report_path)` — Gradio shows download button

### Full report mode (fresh query)
When `is_report=True` and it is NOT a follow-up, the agent runs normally but with `is_report=True` propagated through:
- Agent receives a REPORT MODE hint (full row-level export, no aggregation)
- Codegen receives REPORT MODE instructions in the system prompt
- `_safe_exec` calls `_save_report()` when result is a DataFrame

### File location
```
reports/report_{YYYYMMDD_HHMMSS}.xlsx
```
Merge artifact columns (`_col` suffix where base column already present) are dropped before saving.

---

## 8. RAG System

**File:** `src/rag_retriever.py`

### Collections (ChromaDB Cloud)
- `global_gemini2` — `knowledge/_global/*.md` — business rules, risk framework
- `{module}_gemini2` — `knowledge/{module}/**/*.md` — column definitions, query examples

### Hybrid Retrieval
1. Embed query with Gemini Embedding 2 (`gemini-embedding-2-preview`)
2. Search both collections (`n_results * 2` candidates each)
3. Merge candidates
4. Re-rank: `0.40 × keyword_score + 0.60 × vector_similarity`
5. Return top `n_results` chunks

Falls back to keyword-only if ChromaDB / Gemini unavailable.

### Sync
On first query, new/changed chunks are embedded and upserted to ChromaDB. Only chunks not yet present (by content hash ID) are re-embedded — avoids redundant API calls.

---

## 9. Provider Configuration

### Registry
```python
PROVIDERS = {
    "Typhoon -- v2.5-30b":   typhoon-v2.5-30b-a3b-instruct  (Thai-specialized)
    "Groq -- llama-3.3-70b": llama-3.3-70b-versatile         (default agent/codegen)
    "Groq -- llama-3.1-8b":  llama-3.1-8b-instant            (fast classify)
    "Gemini -- 2.5-flash":   gemini-2.5-flash
    "Gemini 3 Flash":        gemini-3-flash-preview
    "Gemini 3.1 Flash Lite": gemini-3.1-flash-lite-preview
}
```

### Per-Role Routing
```python
ROLE_PROVIDERS = {
    "classify":  "Groq -- llama-3.1-8b",   # hardcoded — fast + cheap
    "summarize": "Typhoon -- v2.5-30b",     # hardcoded — Thai output
    "agent":     None,                       # user-selected
    "codegen":   None,                       # user-selected
}
```

`None` = use the active provider selected in the Gradio dropdown.

### Groq Tool-Use Recovery
Groq's llama models sometimes return tool calls in native `<function=name{...}>` format instead of OpenAI JSON, causing 400 errors. `_recover_tool_call_from_error()` catches these, parses the format, and recovers the tool name + args. Garbled Thai in the recovered args falls back to the original user question.

---

## 10. UI — Key Features (app.py)

### Module / Model dropdowns
- Module: NPL or NPA — switches active table set and RAG collection
- Model: any provider from PROVIDERS — sets agent + codegen provider

### Excel Upload (account list queries)
- `📎` button toggles upload row
- `extract_user_df()` parses Excel/CSV, auto-detects join key column (column name containing รหัส / id / code)
- `df_user` injected into exec scope
- Codegen receives Pattern A (filter portfolio to uploaded IDs) and Pattern B (enrich uploaded file) instructions when `df_user` is present

### Streaming
Generator-based (`run_query` yields strings). UI updates every `_STREAM_INTERVAL` seconds during streaming to avoid flooding Gradio.

### Report Download Button
`gr.DownloadButton` shown only when `run_query` yields a `(text, file_path)` tuple. Hidden otherwise.

### History Tab
Previous reports listed in a dropdown by timestamp. `gr.DownloadButton` for re-downloading past reports.

### Template Manager
Save / load / run named query templates per module. Excel column import: reads headers from an uploaded Excel file and appends them to the prompt textbox.

### Reasoning Accordion
`<details>` block showing: classify model, agent model, codegen model, summarize model, query type, pre-routed table, RAG context chunks, and each `generate_and_run` step (intent, table, code, result preview).

---

## 11. History Cleaning (`_clean_for_history`)

Before passing conversation history to any LLM, `_clean_for_history()` strips:
- `<details>...</details>` blocks (reasoning accordion)
- `💬 **Analysis**` headers
- Period badge lines matching `_BADGE_RE = re.compile(r'\n*-{3,}\n📅[^\n]*')`

This prevents the LLM from copying badge text or reasoning blocks into its responses.

---

## 12. Known Limitations — Free Tier

### Follow-up context is shallow
- Only `_prev_ids` (a set of ID strings) is stored in session — not the previous code or the previous question.
- On follow-up, the agent must reconstruct the full query from `_prev_ids` + the new question. It cannot see *why* those IDs were selected.
- **Root cause of ceiling:** Storing `last_code` was considered but rejected:
  - Groq token limits + tool_use 400 errors make large context injections risky
  - Thai column names in code body corrupt on Groq's `_recover_tool_call_from_error` path
- **Paid-tier upgrade path:** Store `(last_question, last_code)` pair, inject both on follow-up, use a model with a larger context window (e.g., Gemini 1.5 Pro or GPT-4o).

### No full conversation history to LLM
- Famous AIs (ChatGPT, Claude, Gemini) pass the full conversation to the model every turn — context continuity is automatic.
- NS-008 compresses prior turns: for follow-ups, only the last 2 history turns are passed (question + cleaned answer). For fresh questions, only the last question (as `"(answered)"`).
- Free-tier rate limits and token caps make passing full history prohibitively expensive per query.

### Groq rate limits
- `llama-3.1-8b` (classify) and `llama-3.3-70b` (agent/codegen) share the same Groq API key.
- Under heavy use, RPM/TPM limits cause 429 errors. No automatic retry with backoff currently implemented.

### Groq tool_use instability
- Groq's llama models occasionally produce malformed tool call JSON, requiring `_recover_tool_call_from_error()`.
- The recovery strips Thai characters, which can lose meaning in the agent intent. Falls back to original user question in that case.

---

## 13. File Map

```
Natural Stupidity 008/
├── src/
│   ├── app.py              — Gradio UI (module/model dropdowns, streaming chat, upload, history)
│   ├── query_engine.py     — All pipeline logic (~1,871 lines)
│   ├── data_loader.py      — TABLE_REGISTRY, load_table(), schema generation (175 lines)
│   ├── rag_retriever.py    — Hybrid RAG: keyword + Gemini Embedding 2 + ChromaDB Cloud
│   └── template_manager.py — Save/load/run named query templates
├── data/
│   ├── test3 NPL/          — NPL source files (CSV outstanding/outstandingcol, Excel collection)
│   ├── test3 NPA/          — NPA source files (Excel outstanding + collection)
│   └── cache/              — Auto-generated parquet files (delete to force reload)
├── knowledge/
│   ├── _global/            — business_rules.md, risk_framework.md
│   ├── npl/                — columns.md, collection_groups.md, query_examples.md
│   │   ├── outstanding/    — outstanding-specific column notes
│   │   ├── outstandingcol/ — collateral-specific column notes
│   │   └── collection/     — collection-specific column notes
│   └── npa/                — columns.md, query_examples.md
│       ├── outstanding/
│       └── collection/
├── reports/                — Auto-saved Excel exports (report_YYYYMMDD_HHMMSS.xlsx)
├── flow/
│   ├── chatbot_flow.xml    — draw.io architecture diagram
│   └── Activity Flow Diagram (2).html
├── SYSTEM.md               — This document
├── question_examples.md    — 8-section test case reference
└── .env                    — API keys (TYPHOON_API_KEY, GROQ_API_KEY, GEMINI_API_KEY, CHROMA_*)
```

---

## 14. Environment Setup

### Python
Python 3.13 · venv at `.venv`

### Dependencies (requirements.txt)
```
openai          — provider API calls (OpenAI-compatible interface)
google-genai    — Gemini + Gemini Embedding 2
chromadb        — ChromaDB Cloud client
pandas
openpyxl        — Excel read/write
pyarrow         — parquet cache
tabulate
python-dotenv
gradio
plotly
```

### .env keys
```
TYPHOON_API_KEY   — Typhoon v2.5-30b (summarize)
GROQ_API_KEY      — Groq llama models (classify + agent/codegen)
GEMINI_API_KEY    — Gemini models + Gemini Embedding 2 (RAG)
CHROMA_API_KEY    — ChromaDB Cloud
CHROMA_TENANT     — ChromaDB Cloud tenant
CHROMA_DATABASE   — ChromaDB Cloud database name
```

### Run
```bash
cd "Natural Stupidity 008/src"
python app.py
```
Gradio serves on `http://localhost:7860` by default.

---

## 15. Planned Next Steps

| Phase | Item |
|---|---|
| Short-term | Full live QA with real queries across all query types |
| Short-term | DB access via SQLAlchemy when credentials available |
| Phase 2 | Text-to-SQL against a live database (replace CSV/Excel) |
| Phase 2 | Paid-tier follow-up context: store `(last_question, last_code)`, inject on follow-up |
| Phase 3 | FastAPI backend + React frontend |
| Phase 3 | Multi-user session management (replace thread-local with session tokens) |

---

*Last updated: 2026-05-11*
