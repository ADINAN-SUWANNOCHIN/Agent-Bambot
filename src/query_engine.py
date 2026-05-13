"""
query_engine.py -- Architecture 3.0

Flow per query:
  1. classify()        -- fast model, short prompt  → data_query | analytical | out_of_scope
  2. analytical        -- stream analyst directly (no agent needed)
  3. pre_route()       -- deterministic domain rules → table choice
  4. _route_table()    -- LLM fallback when pre_route returns None
  5. _run_agent_loop() -- orchestrator agent (short prompt, no schemas)
       tools: retrieve_knowledge, generate_and_run, finish
       generate_and_run → specialist code-gen LLM (full schema + code rules)
  6. _update_session() -- store result IDs for follow-up queries
  7. stream analysis   -- Typhoon / active provider, Thai output
"""
import datetime
import html as _html
import json
import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
import pandas as pd
from dotenv import load_dotenv
from rag_retriever import retrieve as rag_retrieve, set_module as rag_set_module
from data_loader import load_table, get_schema_description, get_tables, TABLE_REGISTRY, TABLE_LABELS

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

REPORTS_DIR = Path(__file__).parent.parent / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

SHOW_REASONING = True

# ── Thai month display map (for period badge in responses) ─────────────────────
_MONTH_THAI: dict[str, str] = {
    'Jan': 'มกราคม',  'Feb': 'กุมภาพันธ์', 'Mar': 'มีนาคม',    'Apr': 'เมษายน',
    'May': 'พฤษภาคม', 'Jun': 'มิถุนายน',   'Jul': 'กรกฎาคม',   'Aug': 'สิงหาคม',
    'Sep': 'กันยายน', 'Oct': 'ตุลาคม',     'Nov': 'พฤศจิกายน', 'Dec': 'ธันวาคม',
    'January': 'มกราคม',  'February': 'กุมภาพันธ์', 'March': 'มีนาคม',
    'April': 'เมษายน',    'June': 'มิถุนายน',       'July': 'กรกฎาคม',
    'August': 'สิงหาคม',  'September': 'กันยายน',   'October': 'ตุลาคม',
    'November': 'พฤศจิกายน', 'December': 'ธันวาคม',
}

# ── Thai table descriptions for clarification questions ────────────────────────
_TABLE_THAI_DESC: dict[str, dict[str, str]] = {
    "npl": {
        "outstanding":    "ลูกหนี้คงค้าง — ยอดหนี้, TDR/Non-TDR, กลุ่มงาน, หลักประกัน",
        "outstandingcol": "รายการหลักประกัน — ที่ดิน/อาคาร, ราคาประเมิน, จังหวัด",
        "collection":     "ผลเรียกเก็บ — Cash Non TDR, LGO1, แยกกลุ่มงาน/พนักงาน",
    },
    "npa": {
        "outstanding": "ทรัพย์คงค้าง — ราคาประเมิน, ต้นทุน, ระยะเวลาถือครอง, เกรด",
        "collection":  "ผลเรียกเก็บ NPA — จังหวัด, เขต, ประเภททรัพย์",
    },
}

# ── Pipeline logger ────────────────────────────────────────────────────────────
_LOG_SEP = "─" * 72

def _log(tag: str, **fields) -> None:
    print(f"\n{_LOG_SEP}\n▶ {tag}")
    for k, v in fields.items():
        s = str(v)
        if len(s) > 1200:
            s = s[:1200] + f"\n  ... [{len(str(v)) - 1200} more chars]"
        s = s.replace("\n", "\n    ")
        print(f"  {k}: {s}")
    print(_LOG_SEP)

# ── Provider registry ──────────────────────────────────────────────────────────
PROVIDERS: dict[str, dict] = {
    "Typhoon -- v2.5-30b": {
        "type": "openai",
        "api_key_env": "TYPHOON_API_KEY",
        "base_url": "https://api.opentyphoon.ai/v1",
        "model": "typhoon-v2.5-30b-a3b-instruct",
        "max_tokens": 16384,
    },
    "Groq -- llama-3.3-70b": {
        "type": "openai",
        "api_key_env": "GROQ_API_KEY",
        "base_url": "https://api.groq.com/openai/v1",
        "model": "llama-3.3-70b-versatile",
        "max_tokens": 8192,
    },
    "Groq -- llama-3.1-8b": {
        "type": "openai",
        "api_key_env": "GROQ_API_KEY",
        "base_url": "https://api.groq.com/openai/v1",
        "model": "llama-3.1-8b-instant",
        "max_tokens": 8192,
    },
    "Gemini -- 2.5-flash": {
        "type": "gemini",
        "api_key_env": "GEMINI_API_KEY",
        "model": "gemini-2.5-flash",
    },
    "Gemini 3 Flash": {
        "type": "gemini",
        "api_key_env": "GEMINI_API_KEY",
        "model": "gemini-3-flash-preview",
    },
    "Gemini 3.1 Flash Lite": {
        "type": "gemini",
        "api_key_env": "GEMINI_API_KEY",
        "model": "gemini-3.1-flash-lite-preview",
    },
}

# ── Per-role provider overrides ────────────────────────────────────────────────
# Set a provider name to use a specific model for that role.
# None = use the active (user-selected) provider.
ROLE_PROVIDERS: dict[str, str | None] = {
    "classify": "Groq -- llama-3.1-8b",        # fast + cheap for short classification
    "agent":    None,                            # orchestrator -- user-selected
    "codegen":  None,                            # specialist code writer -- user-selected
    "summarize": "Typhoon -- v2.5-30b",          # Thai-specialized; falls back to user-selected if key missing
}

DEFAULT_PROVIDER = "Groq -- llama-3.3-70b"
_active_provider = DEFAULT_PROVIDER
_client_cache: dict = {}


def set_provider(name: str) -> None:
    global _active_provider
    if name not in PROVIDERS:
        raise ValueError(f"Unknown provider: {name}")
    _active_provider = name


def _get_or_create_client(cfg: dict):
    key = cfg["api_key_env"] + cfg.get("base_url", "gemini")
    if key in _client_cache:
        return _client_cache[key]
    if cfg["type"] == "openai":
        from openai import OpenAI
        _client_cache[key] = OpenAI(
            api_key=os.environ.get(cfg["api_key_env"]),
            base_url=cfg["base_url"],
        )
    else:
        from google import genai
        _client_cache[key] = genai.Client(api_key=os.environ.get(cfg["api_key_env"]))
    return _client_cache[key]


def _resolve_provider(role: str) -> str:
    """Return the provider name to use for a given role."""
    name = ROLE_PROVIDERS.get(role)
    if name and name in PROVIDERS:
        cfg = PROVIDERS[name]
        if os.environ.get(cfg["api_key_env"], ""):
            return name
    return _active_provider


# ── Core LLM calls ─────────────────────────────────────────────────────────────

def _call_llm(
    system: str, messages: list[dict], temperature: float = 0.0, role: str = "agent"
) -> str:
    provider_name = _resolve_provider(role)
    cfg = PROVIDERS[provider_name]
    client = _get_or_create_client(cfg)

    if cfg["type"] == "gemini":
        from google.genai import types
        contents = [
            types.Content(
                role="model" if m["role"] == "assistant" else "user",
                parts=[types.Part(text=m["content"])],
            )
            for m in messages
        ]
        response = client.models.generate_content(
            model=cfg["model"],
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system, temperature=temperature
            ),
        )
        text = response.text
        if not text:
            reason = getattr((getattr(response, "candidates", [None]) or [None])[0], "finish_reason", "unknown")
            raise RuntimeError(f"[{provider_name}] Gemini returned empty response (finish_reason={reason})")
        return text
    else:
        all_messages = [{"role": "system", "content": system}] + messages
        response = client.chat.completions.create(
            model=cfg["model"],
            messages=all_messages,
            temperature=temperature,
            max_tokens=cfg.get("max_tokens", 8192),
        )
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError(f"[{provider_name}] API returned empty response")
        return content


def _call_llm_stream(
    system: str, messages: list[dict], temperature: float = 0.0, role: str = "summarize"
):
    provider_name = _resolve_provider(role)
    cfg = PROVIDERS[provider_name]
    client = _get_or_create_client(cfg)
    yielded = False

    if cfg["type"] == "gemini":
        from google.genai import types
        contents = [
            types.Content(
                role="model" if m["role"] == "assistant" else "user",
                parts=[types.Part(text=m.get("content", ""))],
            )
            for m in messages
            if m["role"] in ("user", "assistant")
        ]
        for chunk in client.models.generate_content_stream(
            model=cfg["model"],
            contents=contents,
            config=types.GenerateContentConfig(system_instruction=system, temperature=temperature),
        ):
            if chunk.text:
                yield chunk.text
                yielded = True
    else:
        all_msgs = [{"role": "system", "content": system}] + [
            {"role": m["role"], "content": m.get("content", "")}
            for m in messages
            if m["role"] in ("user", "assistant")
        ]
        stream = client.chat.completions.create(
            model=cfg["model"],
            messages=all_msgs,
            temperature=temperature,
            max_tokens=cfg.get("max_tokens", 8192),
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
                yielded = True

    if not yielded:
        yield f"[{provider_name}] No response received -- please retry or switch provider."


# ── Tool definitions + agent message types ─────────────────────────────────────

def _get_agent_tools(module: str) -> list:
    tables = (
        ["outstanding", "outstandingcol", "collection", "outstanding+outstandingcol"]
        if module == "npl"
        else ["outstanding", "collection"]
    )
    return [
        {
            "type": "function",
            "function": {
                "name": "retrieve_knowledge",
                "description": "Retrieve domain knowledge (column rules, business logic, query patterns) from the knowledge base. Call when you need context before generating a query.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query in Thai or English"}
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "generate_and_run",
                "description": "Describe what to compute in plain language -- a specialist will write and execute the pandas code. Returns the result and the code that ran.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "intent": {
                            "type": "string",
                            "description": "What to compute, clearly stated. Include filter conditions, aggregation type, and any period constraints.",
                        },
                        "table": {
                            "type": "string",
                            "description": "Which table to query.",
                            "enum": tables,
                        },
                    },
                    "required": ["intent", "table"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "finish",
                "description": "Signal that you have the data you need. Call after generate_and_run gives a valid result.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
    ]


@dataclass
class _ToolCall:
    id: str
    name: str
    args: dict


@dataclass
class _AgentResponse:
    finish_reason: str
    content: str | None = None
    tool_calls: list[_ToolCall] = field(default_factory=list)


# ── Message format converters ──────────────────────────────────────────────────

def _to_openai_messages(messages: list[dict]) -> list[dict]:
    result = []
    for m in messages:
        if m["role"] == "tool":
            result.append({"role": "tool", "content": m["content"], "tool_call_id": m["tool_call_id"]})
        elif m["role"] == "assistant" and m.get("_tool_calls"):
            result.append({
                "role": "assistant",
                "content": m.get("content"),
                "tool_calls": [
                    {"id": tc["id"], "type": "function",
                     "function": {"name": tc["name"], "arguments": json.dumps(tc["args"])}}
                    for tc in m["_tool_calls"]
                ],
            })
        else:
            result.append({"role": m["role"], "content": m.get("content", "")})
    return result


def _to_gemini_contents(messages: list[dict]):
    from google.genai import types
    contents = []
    for m in messages:
        if m["role"] == "user":
            contents.append(types.Content(role="user", parts=[types.Part(text=m["content"] or "")]))
        elif m["role"] == "assistant":
            parts = []
            if m.get("content"):
                parts.append(types.Part(text=m["content"]))
            for tc in m.get("_tool_calls", []):
                parts.append(types.Part(function_call=types.FunctionCall(name=tc["name"], args=tc["args"])))
            contents.append(types.Content(role="model", parts=parts or [types.Part(text="")]))
        elif m["role"] == "tool":
            contents.append(types.Content(role="user", parts=[
                types.Part(function_response=types.FunctionResponse(
                    name=m["tool_name"], response={"result": m["content"]}
                ))
            ]))
    return contents


def _gemini_func_declarations(tools: list):
    from google.genai import types
    return [
        types.FunctionDeclaration(
            name=t["function"]["name"],
            description=t["function"]["description"],
            parameters=t["function"].get("parameters", {"type": "object", "properties": {}}),
        )
        for t in tools
    ]


def _recover_tool_call_from_error(exc: Exception, messages: list[dict]) -> "_AgentResponse | None":
    """Parse a 400 tool_use_failed body and reconstruct the intended tool call.

    Some llama models emit native <function=name{...}> syntax instead of the
    OpenAI JSON format; Groq rejects these with 400. The failed text is in
    exc.body['error']['failed_generation']. We extract the tool name and args,
    falling back to the last user message as the query when args are garbled.
    """
    try:
        status = getattr(exc, "status_code", "?")
        body   = getattr(exc, "body", None)
        print(f"[tool_use_failed] caught | status={status} | body_type={type(body).__name__} | body={str(body)[:400]}")

        # Primary: body dict — Groq returns the error dict flat (no nested 'error' key)
        error: dict = {}
        if isinstance(body, dict):
            # Handle both flat {'code': ..., 'failed_generation': ...}
            # and nested {'error': {'code': ..., 'failed_generation': ...}}
            error = body.get("error") or body
            print(f"[tool_use_failed] body is dict | code={error.get('code')} | fg_present={'failed_generation' in error}")

        if error.get("code") != "tool_use_failed":
            # Fallback: body is None or unrecognised — scan str(exc) for the pattern directly
            exc_str = str(exc)
            print(f"[tool_use_failed] primary miss — scanning str(exc) | tool_use_failed_found={'tool_use_failed' in exc_str}")
            if "tool_use_failed" not in exc_str:
                print("[tool_use_failed] not a tool_use_failed error — skipping recovery")
                return None
            # Search for the native call pattern directly rather than parsing around quotes
            fg_direct = re.search(r'(<function=\w+.*?)(?:\\n|\\\'|\'[,}]|$)', exc_str, re.DOTALL)
            fg = fg_direct.group(1) if fg_direct else ""
            print(f"[tool_use_failed] str fallback | fg_found={bool(fg)} | fg={fg[:200]}")
            error = {"code": "tool_use_failed", "failed_generation": fg}

        fg = error.get("failed_generation", "")
        print(f"[tool_use_failed] fg='{fg[:400]}'")

        # Handle both <function=name{"args"}> and <function=name>{"args"} formats
        m = re.search(r'<function=(\w+)[>\s]*(\{.*?\})', fg, re.DOTALL)
        if not m:
            print("[tool_use_failed] regex did not match — cannot recover")
            return None

        tool_name = m.group(1)
        try:
            args = json.loads(m.group(2))
        except (json.JSONDecodeError, ValueError):
            args = {}
            print(f"[tool_use_failed] args JSON parse failed for: {m.group(2)[:100]}")

        if tool_name == "retrieve_knowledge":
            q = args.get("query", "")
            last_user = next(
                (msg["content"] for msg in reversed(messages) if msg.get("role") == "user"), ""
            )
            # Garbling check 1: empty or low character diversity
            garbled = not q or len(set(q)) < max(4, len(q) // 8)
            # Garbling check 2: Thai text with zero word overlap with original question
            if not garbled and any('฀' <= c <= '๿' for c in q):
                orig_words = set(last_user.lower().split())
                q_words = set(q.lower().split())
                if not orig_words.intersection(q_words):
                    garbled = True
            if garbled:
                args = {"query": last_user[:300]}
                print(f"[tool_use_failed] garbled retrieve_knowledge query → using original user question")

        print(f"[tool_use_failed] RECOVERED | tool={tool_name} | args={args}")
        return _AgentResponse(
            finish_reason="tool_calls",
            tool_calls=[_ToolCall(id="recovered_0", name=tool_name, args=args)],
        )
    except Exception as inner:
        print(f"[tool_use_failed] recovery itself threw: {inner}")
        return None


def _call_llm_with_tools(
    system: str, messages: list[dict], tools: list, role: str = "agent"
) -> _AgentResponse:
    provider_name = _resolve_provider(role)
    cfg = PROVIDERS[provider_name]
    client = _get_or_create_client(cfg)

    if cfg["type"] == "gemini":
        from google.genai import types
        contents = _to_gemini_contents(messages)
        response = client.models.generate_content(
            model=cfg["model"],
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system,
                tools=[types.Tool(function_declarations=_gemini_func_declarations(tools))],
                temperature=0.0,
            ),
        )
        candidate = response.candidates[0]
        tcs, text_parts = [], []
        for i, part in enumerate(candidate.content.parts):
            if hasattr(part, "function_call") and part.function_call and part.function_call.name:
                fc = part.function_call
                tcs.append(_ToolCall(id=f"{fc.name}_{i}", name=fc.name, args=dict(fc.args)))
            elif hasattr(part, "text") and part.text:
                text_parts.append(part.text)
        text = "".join(text_parts)
        if tcs:
            return _AgentResponse(finish_reason="tool_calls", content=text or None, tool_calls=tcs)
        return _AgentResponse(finish_reason="stop", content=text)
    else:
        oai_msgs = [{"role": "system", "content": system}] + _to_openai_messages(messages)
        try:
            response = client.chat.completions.create(
                model=cfg["model"],
                messages=oai_msgs,
                tools=tools,
                tool_choice="auto",
                temperature=0.0,
                max_tokens=cfg.get("max_tokens", 8192),
            )
        except Exception as exc:
            recovered = _recover_tool_call_from_error(exc, messages)
            if recovered is not None:
                return recovered
            raise
        msg = response.choices[0].message
        if msg.tool_calls:
            return _AgentResponse(
                finish_reason="tool_calls",
                content=msg.content,
                tool_calls=[
                    _ToolCall(id=tc.id, name=tc.function.name, args=json.loads(tc.function.arguments))
                    for tc in msg.tool_calls
                ],
            )
        return _AgentResponse(finish_reason="stop", content=msg.content)


# ── Pre-routing (deterministic domain rules) ───────────────────────────────────
# Copied from test01 -- hard-won Thai domain knowledge, zero LLM cost.

TABLE_DESCRIPTIONS: dict[str, dict[str, str]] = {
    "npl": {
        "outstanding": (
            "Debtor-level snapshot. One row = one debtor (key: รหัสลูกหนี้). "
            "Use for: debtor counts, total debt (ภาระหนี้คงเหลือ), principal (เงินต้นคงเหลือ), "
            "collateral value (มูลค่าหลักประกัน), collateral count per debtor (จำนวนทรัพย์หลักประกัน), "
            "TDR/Non-TDR status (สถานะการประนอมหนี้), collection group codes (01-07), "
            "asset grade (เกรดทรัพย์: A/B/C/D), Yield, CEIR, Secured/Clean Loan status. "
            "NOT for: per-item collateral type/status or province of collateral."
        ),
        "outstandingcol": (
            "Collateral-level snapshot. One row = one collateral item (NOT one debtor). "
            "Use for: collateral type (ประเภทหลักประกัน), collateral sub-type (ประเภทย่อยหลักประกัน), "
            "collateral status (สถานะหลักประกัน), province of collateral (ที่อยู่ทรัพย์ - จังหวัด), "
            "land area (ไร่/ตรว.), document number (เลขที่เอกสารสิทธิ์), "
            "collateral piece count (จำนวนทรัพย์หลักประกัน — pre-computed, never .sum()). "
            "Links to outstanding via รหัสลูกหนี้. For debtor counts: use .nunique()."
        ),
        "collection": (
            "Monthly payment events. One row = one payment. "
            "Use for: cash collected (ผลเรียกเก็บ), CASH column, LGO1 column, monthly trends."
        ),
    },
    "npa": {
        "outstanding": (
            "Asset-level snapshot. One row = one property (key: รหัสตลาด). "
            "Use for: asset counts, appraisal (ราคาประเมิน), asking price (ราคาตั้งขาย), "
            "cost (ต้นทุนรวม), holding period (ระยะเวลาถือครอง NPA (ปี)), "
            "asset grade (A/B/C/D), province (จังหวัด), asset type (ประเภทสินทรัพย์)."
        ),
        "collection": (
            "Monthly NPA payment events. "
            "Use for: Full Payment, Installment Payment, Others, Total Actual."
        ),
    },
}

_ROUTER_SYSTEM = """\
You are a table router for a financial portfolio assistant.
Given the user's question, choose which table(s) to query.

Rules:
- Money received, payments, ผลเรียกเก็บ, เงินรับ, CASH, LGO1 → "collection"
- Collateral items, land area, document numbers, province of collateral, piece count (NPL) → "outstandingcol"
- Debtor/asset counts, balances, portfolio overview, TDR status, asset details → "outstanding"
- Needs BOTH debtor info AND per-piece collateral details (NPL only) → "outstanding+outstandingcol"
- NPA has NO outstandingcol. For NPA only use: outstanding | collection.
- When in doubt → "outstanding"

Reply with ONLY one of: outstanding | outstandingcol | collection | outstanding+outstandingcol
"""

_NPL_FORCE_COL = [
    "ชิ้น", "จำนวนชิ้น", "จำนวนทรัพย์หลักประกัน",
    "จังหวัด", "อำเภอ", "ตำบล", "โซน",
    "ไร่", "ตารางวา", "เลขที่เอกสาร", "เลขที่โฉนด", "โฉนด",
    "พื้นที่", "หลักประกันทั้งหมด", "ทรัพย์หลักประกัน", "เลขที่เอกสารสิทธิ์",
    "ประเภทหลักประกัน", "ประเภทย่อยหลักประกัน", "สถานะหลักประกัน",
]


def _pre_route(question: str, module: str, history: list[dict] | None = None) -> str | None:
    q = question.lower()

    if module == "npl":
        _OUTSTANDING_FILTER_KW = ["tdr", "non-tdr", "ประนอมหนี้"]
        _COL_DETAIL_KW = [
            "จังหวัด", "อำเภอ", "ตำบล", "ไร่", "ตารางวา", "ตรว", "ตรม",
            "โฉนด", "เลขที่เอกสาร", "กี่ชิ้น", "จำนวนชิ้น", "ที่ดิน", "ตั้งอยู่", "อยู่ที่ไหน",
        ]
        if any(kw in q for kw in _OUTSTANDING_FILTER_KW) and any(kw in q for kw in _COL_DETAIL_KW):
            return "outstanding+outstandingcol"

        if any(kw in q for kw in _NPL_FORCE_COL):
            return "outstandingcol"

        _DISPLAY_WORDS = ["แสดง", "ขอดู", "รายการ", "ดูหลักประกัน", "list"]
        # "มูลค่าหลักประกัน" is in outstanding (debtor-level value), NOT outstandingcol (item list)
        if "หลักประกัน" in q and "มูลค่า" not in q and any(dw in q for dw in _DISPLAY_WORDS):
            return "outstandingcol"

        # สังหาริมทรัพย์/TFRS = debtor-level classification → always outstanding.
        # Display queries (แสดงหลักประกัน...) are already caught by the rule above.
        # Per-item queries (ประเภทหลักประกัน...) are caught by _NPL_FORCE_COL.
        if any(kw in q for kw in ["สังหาริมทรัพย์", "ไม่ใช่สังหาริมทรัพย์", "tfrs"]):
            return "outstanding"

        _ITEM_FILTER = ["เกรด", "ประเภทหลักประกัน", "ประเภทย่อย", "สถานะหลักประกัน"]
        if "หลักประกัน" in q and any(fw in q for fw in _ITEM_FILTER) and "มูลค่า" not in q:
            return "outstandingcol"

        _FOLLOWUP_MARKERS = [
            "รายนี้", "รายเหล่านี้", "กลุ่มนี้", "คนเหล่านี้", "คนนี้",
            "รายการนี้", "รายการเหล่านี้", "กลุ่มลูกหนี้นี้", "ทรัพย์เหล่านี้",
        ]
        _FOLLOWUP_NUM = re.compile(r'\d+\s*(?:คนนี้|รายนี้|รายการนี้)')
        followup = any(kw in q for kw in _FOLLOWUP_MARKERS) or bool(_FOLLOWUP_NUM.search(q))
        _OUTSTANDING_DATA_KW = ["จ่ายเงิน", "ภาระหนี้", "หนี้เหลือ", "เงินต้น", "เงินรับ", "ผลเรียกเก็บ", "เก็บได้", "cash", "ยอดหนี้"]
        if followup and any(kw in q for kw in _OUTSTANDING_DATA_KW) and history:
            recent_qs = [h.get("question", "").lower() for h in history[-3:]]
            if any(any(kw in hq for kw in ["ชิ้น", "จำนวนทรัพย์", "จำนวนชิ้น"]) for hq in recent_qs):
                return "outstanding+outstandingcol"

    _COLL_KW = ["ผลเรียกเก็บ", "เงินรับ", "เก็บได้", "lgo1", "full payment", "installment"]
    if any(kw in q for kw in _COLL_KW):
        return "collection"
    return None


def _route_table(question: str, module: str, history: list[dict], rag_context: str = "") -> str:
    available = TABLE_DESCRIPTIONS.get(module, {})
    desc_lines = "\n".join(f"- {name}: {desc}" for name, desc in available.items())
    rag_block = f"\n\nRelevant knowledge:\n{rag_context}" if rag_context else ""
    system = _ROUTER_SYSTEM + f"\n\nAvailable tables for {module.upper()}:\n{desc_lines}" + rag_block
    messages = _history_messages(history[-2:])
    messages.append({"role": "user", "content": question})
    _log("ROUTE-TABLE (LLM fallback)", question=question)
    result = _call_llm(system, messages, temperature=0.0, role="classify").strip().lower()
    valid = list(available.keys()) + ["outstanding+outstandingcol"]
    for v in valid:
        if v in result:
            _log("ROUTE-TABLE result", table=v)
            return v
    _log("ROUTE-TABLE result", table="outstanding (default)")
    return "outstanding"


# ── Classifier ─────────────────────────────────────────────────────────────────

_CLASSIFIER_SYSTEM = """\
You are a scope classifier for an NPL/NPA financial portfolio assistant.
Work through the decision tree below in order. Stop at the first match.

STEP 1 — OUT OF SCOPE
Is the question completely unrelated to loans, assets, debt collection, or finance?
→ out_of_scope

STEP 2 — CLARIFICATION
Does the question have NO specific subject, metric, or filter — just a bare request with no
actionable target? Examples: "ขอดูหน่อย", "ขอดูตาราง", "แสดงหน่อย", "ขอรายงาน",
"give me a table", "show me something", "อยากได้ข้อมูล".
A question that says only "show/view/give + table/data/report" with nothing else.
→ clarification
CONSERVATIVE: if the intent is even partially clear, skip this step and continue.

STEP 3 — PRIMARY INTENT
Ask yourself: what is the PRIMARY reason the user is asking this?

A. PRIMARY intent is to UNDERSTAND, EXPLAIN, or REASON about something — no request for
   actual data records:
   Signals: คืออะไร / หมายความว่า / อธิบาย / ทำไม / ทำไมถึง / เพราะอะไร / explain / what is /
            why / how does / วิธีการ / ความหมาย / เอามาจากไหน / คำนวณยังไง / แน่ใจเหรอ /
            ใช่เหรอ / ตัวเลขนี้มาจากไหน / วิเคราะห์ (without a data pull) /
            แนะนำ (without a data pull)
   IMPORTANT: even if data-count words appear (จำนวน / มากที่สุด / กี่คน), if the question
   is asking WHY or asking for an EXPLANATION, the primary intent is still analytical.
   Example: "ทำไมถึงมีลูกหนี้ TDR จำนวนมาก" → analytical (asking why, not asking to count)
   → analytical

B. PRIMARY intent is BOTH to understand/analyze AND to get actual data records:
   Both signals present in the SAME question:
   - Analytical framing: วิเคราะห์ / แนะนำ / เลือก
   - AND a data pull request: แสดง N ราย / สัก N ราย / ขอตัวอย่าง / ยกตัวอย่าง
   → mixed

C. PRIMARY intent is to COMPUTE, FILTER, COUNT, or DISPLAY actual data:
   Signals: กี่คน / กี่ราย / จำนวน / สูงสุด / อันดับ / top / ranking / แสดง (with specific
            filter or subject) / ขอดู (with specific subject) / มากกว่า / น้อยกว่า /
            group by / filter / count / sum / ผลรวม / เฉลี่ย
   → data_query

D. In doubt → data_query

Reply with ONLY one word: data_query, analytical, mixed, out_of_scope, or clarification\
"""


def _classify(question: str, history: list[dict], rag_context: str = "", module: str = "npl") -> str:
    _tables = get_tables(module)
    _table_list = " / ".join(_tables)
    if module == "npa":
        module_ctx = (
            "\nActive module: NPA -- each record is a property/asset. "
            "ราคาประเมิน/ราคาตั้งขาย/ต้นทุนรวม/ระยะเวลาถือครอง/รหัสตลาด are NPA data terms → data_query."
        )
    else:
        module_ctx = (
            "\nActive module: NPL -- each record is a debtor. "
            "ภาระหนี้/เงินต้น/TDR/ประนอมหนี้/รหัสลูกหนี้/หลักประกัน are NPL data terms → data_query."
        )
    module_ctx += (
        f"\nTables in this module: {_table_list}."
        "\nMeta-questions about what tables or data exist (มีตารางอะไรบ้าง, มีข้อมูลอะไรบ้าง, "
        "what tables do you have, what data is available) → 'analytical'."
    )
    rag_block = f"\n\nContext:\n{rag_context}" if rag_context else ""
    messages = _history_messages(history)
    messages.append({"role": "user", "content": question})
    _log("CLASSIFY", question=question, module=module, history_turns=len(history))
    raw_label = _call_llm(_CLASSIFIER_SYSTEM + module_ctx + rag_block, messages, temperature=0.0, role="classify")
    label = raw_label.strip().lower().split()[0].strip(".,!?;:")
    _log("CLASSIFY raw_label", raw=raw_label.strip(), first_word=label)
    if "out_of_scope" in label:
        _log("CLASSIFY result", label="out_of_scope"); return "out_of_scope"
    if "clarification" in label:
        _log("CLASSIFY result", label="clarification"); return "clarification"
    if "analytical" in label:
        _log("CLASSIFY result", label="analytical"); return "analytical"
    if "mixed" in label:
        _log("CLASSIFY result", label="mixed"); return "mixed"
    _log("CLASSIFY result", label="data_query")
    return "data_query"


_FOLLOWUP_CLASSIFY_SYSTEM = """\
You decide if a question continues or refines the result of a previous query, or is an independent new question.

A question is a FOLLOW-UP if it:
- Refines, filters, or expands the previous result (same subject, different view or narrower/broader scope)
- Implicitly refers to the same records ("เอาแค่ X", "กรองเฉพาะ", "เพิ่มเติม", "ทุก column", "ของกลุ่มนี้")
- Asks for a different column set or time slice of the same dataset

A question is NEW if it:
- Asks about a completely different subject, team, metric, or debtor group
- Starts fresh with its own filter criteria unrelated to the prior result

Reply with ONLY one word: followup or new"""


def _classify_followup(question: str, prev_question: str) -> bool:
    content = f"Previous question: {prev_question}\nCurrent question: {question}"
    try:
        result = _call_llm(_FOLLOWUP_CLASSIFY_SYSTEM, [{"role": "user", "content": content}],
                           temperature=0.0, role="classify").strip().lower()
    except Exception:
        return False
    is_fu = "followup" in result
    _log("FOLLOWUP CLASSIFY", is_followup=is_fu, prev_q=prev_question, question=question)
    return is_fu


# ── Schema helpers ─────────────────────────────────────────────────────────────

def _build_cross_schema(df_main: pd.DataFrame, df_col: pd.DataFrame, module: str,
                        schema_main: str = "", schema_col: str = "") -> str:
    s_main = schema_main or get_schema_description(df_main, module, "outstanding")
    s_col  = schema_col  or get_schema_description(df_col,  module, "outstandingcol")
    return (
        "TWO DataFrames available:\n\n"
        "df  →  outstanding (debtor-level, one row per debtor):\n"
        f"{s_main}\n\n"
        "df_col  →  outstandingcol (collateral-level, one row per collateral item):\n"
        "Join key: 'รหัสลูกหนี้'  (1 debtor : many collateral rows)\n\n"
        f"{s_col}"
    )


def _get_codegen_schema(table: str, dfs: dict, schemas: dict, module: str) -> str:
    if table == "outstanding+outstandingcol":
        return _build_cross_schema(
            dfs["outstanding"], dfs["outstandingcol"], module,
            schemas.get("outstanding", ""), schemas.get("outstandingcol", ""),
        )
    return schemas.get(table, schemas.get("outstanding", ""))


# ── Specialist code-gen ────────────────────────────────────────────────────────

def _build_codegen_system(schema: str, module: str, periods_info: str, is_report: bool = False, df_user_schema: str = "", user_key_col: str = "") -> str:
    if module == "npa":
        module_rules = """\
NPA rules:
- Key column: รหัสตลาด. Do NOT use รหัสลูกหนี้ -- does not exist in NPA.
- Each row = one asset. Use ระยะเวลาถือครอง NPA (ปี) directly for age -- do NOT compute from ปี/เดือน.
- Province: 'จังหวัด' column directly (no prefix for NPA).
- "ลูกหนี้/debtor" context in NPA = assets/รายการ.\
"""
    else:
        module_rules = """\
NPL rules:
- Key column: รหัสลูกหนี้.
- outstandingcol has ONE ROW PER COLLATERAL ITEM. For debtor counts: .nunique() or .drop_duplicates('รหัสลูกหนี้').
- 'จำนวนทรัพย์หลักประกัน' is PRE-COMPUTED per debtor, REPEATED on every collateral row. NEVER .sum()/.mean() it.
  Filter only: df[df['จำนวนทรัพย์หลักประกัน'] > N]
- Province in outstandingcol: 'ที่อยู่ทรัพย์ - จังหวัด' (NOT plain 'จังหวัด').
- TDR STATUS: "อยู่ระหว่างประนอมหนี้" / "กำลังประนอม" / TDR → ALWAYS `df[df['สถานะการประนอมหนี้'] == 'TDR']`
  NEVER use `รหัสชื่อกลุ่มการดำเนินงาน.str.contains('ประนอมหนี้')` — that column is collection groups (01-07), not TDR status.
  'สถานะการประนอมหนี้' contains ONLY the strings 'TDR' or 'Non-TDR'. Use == not str.contains.
- TDR, ภาระหนี้คงเหลือ, เงินต้นคงเหลือ → only in df (outstanding).
- Cross-table (df + df_col available):
    Forward (filter collateral → return debtor info):
      ids = df_col[condition]['รหัสลูกหนี้'].unique()
      result = df[df['รหัสลูกหนี้'].isin(ids)][['col1','col2']]
    Reverse (filter debtor info → return collateral items):
      ids = df[df['ชื่อลูกหนี้'].str.contains('X', na=False)]['รหัสลูกหนี้'].unique()
      result = df_col[df_col['รหัสลูกหนี้'].isin(ids)]\
"""

    id_col = "รหัสลูกหนี้" if module == "npl" else "รหัสตลาด"
    join_col = "รหัสลูกหนี้" if module == "npl" else "รหัสตลาด"
    sec_df   = "df_col" if module == "npl" else "df_coll"

    if is_report:
        report_section = (
            "REPORT MODE — Generate a downloadable DataFrame export:\n"
            "- result must be a DataFrame with ALL matching rows (no aggregation, no counting).\n"
            "- Apply period filter and row filters as normal, then return all matching rows.\n"
            "- Do NOT set result_df — result itself is the final export.\n"
            "- CRITICAL: When merging tables, NEVER enumerate specific column names from the secondary table.\n"
            f"  Always merge the FULL DataFrame to avoid KeyError on unknown column names.\n"
            f"  Correct join pattern (NPL — outstanding + outstandingcol):\n"
            f"    ids = df[filter_condition]['{join_col}'].unique()\n"
            f"    out = df[df['{join_col}'].isin(ids)]\n"
            f"    col = {sec_df}[{sec_df}['{join_col}'].isin(ids)]\n"
            f"    result = out.merge(col, on='{join_col}', how='left', suffixes=('', '_col'))\n"
            f"  If the question only needs one table: just filter + return df or {sec_df} directly.\n"
        )
    else:
        report_section = ""

    if df_user_schema and user_key_col:
        _df_user_section = (
            f"\nUSER-UPLOADED FILE (df_user is in scope):\n"
            f"{df_user_schema}\n\n"
            f"Detected join key: '{user_key_col}'\n\n"
            f"Pattern A — filter portfolio to uploaded accounts:\n"
            f"  ids = df_user['{user_key_col}'].dropna().unique()\n"
            f"  result = df[df['{user_key_col}'].isin(ids)]\n\n"
            f"Pattern B — enrich uploaded data with portfolio columns (อยากได้ทุก column / ขอข้อมูลเพิ่มเติม):\n"
            f"  result = df_user.merge(df, on='{user_key_col}', how='left')\n\n"
            f"Choose A to look up accounts. Choose B to join all portfolio columns onto the uploaded file.\n"
        )
    else:
        _df_user_section = ""

    return f"""\
You are a pandas code specialist for a Thai financial institution.
Write Python/pandas code to answer the given compute intent.
Module: {module.upper()}

{module_rules}

{report_section}
DISPLAY vs COUNT:
  "แสดง / ขอดู / รายชื่อ / list / show"  → result = filtered_df  (NOT len())
  "กี่คน / กี่รายการ / กี่ราย / จำนวน / how many"  → ALWAYS follow this exact pattern:
    filtered_df = df_latest[condition]
    result = filtered_df['{id_col}'].nunique()       # use nunique() to deduplicate across periods
    result_df = filtered_df                          # REQUIRED — ALWAYS set result_df to the filtered rows
  BAD (never write these):
    result = len(df[condition])                      # BAD — no result_df, summarizer gets no context
    result = df[condition]['{id_col}'].nunique()     # BAD — no result_df, summarizer gets no context

MULTI-PERIOD DATA:
{periods_info or 'Data has multiple reporting periods. Use pre-filtered DataFrames for latest period.'}

PERIOD SCOPE — three cases, pick the right one:
  1. default / latest / current / งวดล่าสุด (no specific period mentioned)
     → use df_latest / df_col_latest / df_coll_latest directly. No period filter code needed.
  2. trend / เปรียบเทียบ / แนวโน้ม / YoY / all periods
     → use df / df_col / df_coll. Filter as needed.
  3. user explicitly names a specific period (ธันวาคม, December, Dec, มีนาคม, Mar, ปี 2025, etc.)
     → use df / df_col / df_coll + manual เดือน / ปี filter:
       df_col[df_col['รหัสลูกหนี้'].isin(ids) & (df_col['เดือน'] == 'Dec')]
  NEVER write a period filter to represent "latest/current" — use df_latest for that.
  NEVER reassign df_latest or any scope variable.
  Month format for manual period filters (case 3):
    outstanding / outstandingcol → abbreviated English: 'Jan' 'Feb' 'Mar' ... 'Dec'
    collection (df_coll)         → full English: 'January' 'February' 'March' ... 'December'

CODE RULES:
- Column names: ONLY use columns listed in the Schema section at the bottom. Do NOT use column names from RAG context or conversation history — RAG may reference columns from OTHER tables. If a column name is not in the Schema, do not use it.
- Only use: df, df_col (if available), df_coll (if available), pd, built-in Python.
- NEVER use built-in any()/all() -- use series.any(), series.all().
- Handle NaN: numeric columns → .fillna(0); string/category columns → .dropna() or .fillna('').
- result = DataFrame, Series, or scalar. NEVER a string narrative. NEVER a numpy/arrow array.
- NEVER assign .unique() directly to result — it returns an unrenderable array.
  List unique values: result = pd.Series(df['col'].dropna().unique(), name='col')
  With counts:        result = df['col'].value_counts()
- Categorical columns with EXACT values in schema: use == not str.contains().
- Company/debtor name filters (ชื่อลูกหนี้ / ชื่อบริษัท): ALWAYS use str.contains(name, na=False) not == (names may have spacing or punctuation variants in the data).
- Values are full Thai Baht -- do NOT scale.
- Use 'ME' not 'M', 'YE' not 'Y' for pandas frequency strings (resample/Grouper).
- FOLLOW-UP: if _prev_ids is defined in scope, the question references a previous result.
  Default/latest period — always use the _latest variant:
    df_latest[df_latest['รหัสลูกหนี้'].isin(_prev_ids)]               (NPL outstanding / outstandingcol)
    df_col_latest[df_col_latest['รหัสลูกหนี้'].isin(_prev_ids)]       (NPL collateral — when result is collateral items)
    df_coll_latest[df_coll_latest['รหัสลูกหนี้'].isin(_prev_ids)]     (NPL collection)
    df_latest[df_latest['รหัสตลาด'].isin(_prev_ids)]                  (NPA)
  Specific historical period only (user explicitly names month/year) — use df/df_col/df_coll + period filter.
  Match the table to what is being queried. Only use _prev_ids when question clearly references prior results.
{_df_user_section}
Return ONLY the code block:
```python
# code here
result = ...
```

Schema:
{schema}
"""


def _generate_code(
    intent: str,
    schema: str,
    module: str,
    periods_info: str,
    follow_up_context: str,
    error_hint: str = "",
    rag_context: str = "",
    original_question: str = "",
    is_report: bool = False,
    df_user_schema: str = "",
    user_key_col: str = "",
) -> str:
    system = _build_codegen_system(schema, module, periods_info, is_report=is_report,
                                   df_user_schema=df_user_schema, user_key_col=user_key_col)
    # Original question is the ground truth — agent's intent may paraphrase/lose meaning
    if original_question and original_question.strip() != intent.strip():
        prompt = f"[Original user question (ground truth): {original_question}]\n[Agent intent summary: {intent}]"
    else:
        prompt = intent
    if follow_up_context:
        prompt = f"[Follow-up context: {follow_up_context}]\n\n{prompt}"
    if rag_context:
        prompt = f"[Domain knowledge — business rules and context only. For column names, always use the Schema section, NOT this block:\n{rag_context}\n]\n\n{prompt}"
    if error_hint:
        prompt += f"\n\n[Previous attempt failed: {error_hint}. Fix the code.]"
    messages = [{"role": "user", "content": prompt}]
    _log("CODEGEN → LLM",
         original_question=original_question or "(same as intent)",
         intent=intent,
         rag_context_chars=len(rag_context),
         error_hint=error_hint or "(none)",
         prompt_sent=prompt)
    raw = _call_llm(system, messages, temperature=0.0, role="codegen")
    code = _extract_code(raw)
    _log("CODEGEN ← LLM", code=code)
    return code


# ── Safe code execution ────────────────────────────────────────────────────────

_SAFE_BUILTINS = {
    "len": len, "range": range, "int": int, "float": float, "str": str,
    "list": list, "dict": dict, "set": set, "tuple": tuple, "bool": bool,
    "abs": abs, "round": round, "min": min, "max": max, "sum": sum,
    "sorted": sorted, "enumerate": enumerate, "zip": zip, "map": map,
    "isinstance": isinstance, "print": print,
}


def _safe_exec(code: str, dfs: dict, primary_table: str = "outstanding", is_report: bool = False, df_user: "pd.DataFrame | None" = None) -> tuple[str, object, object]:
    local_vars: dict = {"pd": pd}

    # Primary df = the queried table
    primary = "outstanding" if primary_table == "outstanding+outstandingcol" else primary_table
    local_vars["df"] = dfs.get(primary, pd.DataFrame()).copy()

    # Secondary dfs always available
    if "outstandingcol" in dfs:
        local_vars["df_col"] = dfs["outstandingcol"].copy()
    if "collection" in dfs:
        local_vars["df_coll"] = dfs["collection"].copy()

    if df_user is not None:
        local_vars["df_user"] = df_user.copy()

    # Session follow-up IDs (real IDs from previous query, not re-derived)
    session = _get_session()
    if session.get("last_debtor_ids"):
        local_vars["_prev_ids"] = session["last_debtor_ids"]

    # Dynamic period variables — computed from actual data every call, never hardcoded
    _out_df  = dfs.get("outstanding", pd.DataFrame())
    _coll_df = dfs.get("collection",  pd.DataFrame())
    if 'ปี' in _out_df.columns and len(_out_df) > 0:
        _ly = int(_out_df['ปี'].max())
        _mo_s = _out_df[_out_df['ปี'] == _ly]['เดือน']
        local_vars['_latest_year']  = _ly
        local_vars['_latest_month'] = str(_mo_s.mode().iloc[0]) if len(_mo_s) > 0 else 'Mar'
    if 'ปี' in _coll_df.columns and len(_coll_df) > 0:
        _cy  = int(_coll_df['ปี'].max())
        _mc_s = _coll_df[_coll_df['ปี'] == _cy]['เดือน']
        local_vars['_latest_month_coll'] = str(_mc_s.mode().iloc[0]) if len(_mc_s) > 0 else 'March'

    # Pre-filtered DataFrames — codegen uses df_latest/df_col_latest/df_coll_latest directly.
    # Each is filtered to its own latest ปี+เดือน so month format is always correct per table.
    for _pf_var, _pf_src in [
        ('df_latest',      local_vars.get('df',      pd.DataFrame())),
        ('df_col_latest',  local_vars.get('df_col')),
        ('df_coll_latest', local_vars.get('df_coll')),
    ]:
        if _pf_src is None:
            continue
        if 'ปี' not in _pf_src.columns or len(_pf_src) == 0:
            local_vars[_pf_var] = _pf_src.copy()
            continue
        _pf_ly = int(_pf_src['ปี'].max())
        _pf_rows = _pf_src[_pf_src['ปี'] == _pf_ly]
        if 'เดือน' in _pf_src.columns and len(_pf_rows) > 0:
            _pf_lm = str(_pf_rows['เดือน'].mode().iloc[0])
            local_vars[_pf_var] = _pf_src[(_pf_src['ปี'] == _pf_ly) & (_pf_src['เดือน'] == _pf_lm)].copy()
        else:
            local_vars[_pf_var] = _pf_rows.copy()

    try:
        exec(code, {"__builtins__": _SAFE_BUILTINS}, local_vars)  # noqa: S102
        raw = local_vars.get("result", "(no result set)")
        rdf = local_vars.get("result_df")
        # Normalize numpy/arrow arrays → pd.Series so display works cleanly.
        # .unique() returns ArrowStringArray which stringifies as ugly <ArrowStringArray>[...]
        if not isinstance(raw, (pd.DataFrame, pd.Series, int, float, bool, str, type(None))):
            if hasattr(raw, "__iter__") and not isinstance(raw, dict):
                try:
                    raw = pd.Series(list(raw))
                except Exception:
                    pass
        if is_report and isinstance(raw, pd.DataFrame) and len(raw) > 0:
            report_path = _save_report(raw)
            _get_session()["last_report_file"] = report_path
            _log("REPORT SAVED", path=report_path, rows=len(raw), cols=len(raw.columns))
        return str(raw)[:3000], raw, rdf
    except Exception as exc:
        return f"ERROR: {exc}", None, None


# ── Session state (thread-local for multi-user safety) ────────────────────────

_session_local = threading.local()


def _get_session() -> dict:
    if not hasattr(_session_local, "data"):
        _session_local.data = {
            "last_debtor_ids":  None,
            "last_table":       None,
            "last_module":      None,
            "last_report_file": None,
            "last_report_rows": 0,
            "last_report_cols": 0,
            "last_raw_result":  None,
        }
    return _session_local.data


def _update_session(result: dict, module: str, table: str) -> None:
    raw = result.get("raw_result")
    rdf = result.get("result_df")
    session = _get_session()
    session["last_table"] = table
    session["last_module"] = module
    id_col = "รหัสลูกหนี้" if module == "npl" else "รหัสตลาด"
    # Display queries: raw is a DataFrame with IDs.
    # Count queries: raw is a scalar but result_df holds the filtered rows.
    target = None
    if isinstance(raw, pd.DataFrame) and id_col in raw.columns:
        target = raw
    elif isinstance(rdf, pd.DataFrame) and id_col in rdf.columns:
        target = rdf
    if target is not None:
        ids = set(target[id_col].dropna().astype(str).unique().tolist())
        session["last_debtor_ids"] = ids if ids else None
    else:
        session["last_debtor_ids"] = None
    # Store full result DataFrame for follow-up export (export previous result without re-query)
    if isinstance(raw, pd.DataFrame) and len(raw) > 0:
        session["last_raw_result"] = raw
    elif isinstance(rdf, pd.DataFrame) and len(rdf) > 0:
        session["last_raw_result"] = rdf
    else:
        session["last_raw_result"] = None


def _build_followup_context(module: str) -> str:
    """Build the _prev_ids context hint. Call only when is_followup is confirmed True."""
    session = _get_session()
    if not session.get("last_debtor_ids"):
        return ""
    id_col = "รหัสลูกหนี้" if module == "npl" else "รหัสตลาด"
    n = len(session["last_debtor_ids"])
    last_table = session.get("last_table", "outstanding")
    if last_table == "collection":
        filter_hint = f"df_coll_latest[df_coll_latest['{id_col}'].isin(_prev_ids)]"
    else:
        filter_hint = f"df_latest[df_latest['{id_col}'].isin(_prev_ids)]"
    return (
        f"Follow-up query. Previous result contained {n} unique {id_col} values. "
        f"They are stored in `_prev_ids` (set in scope). "
        f"Filter the current DataFrame with: {filter_hint} "
        f"(use the _latest variant for default/current period; use df/df_col/df_coll only if user explicitly requests a specific historical period)"
    )


# ── Report helpers ────────────────────────────────────────────────────────────

_REPORT_KEYWORDS = [
    "รายงาน", "ส่งออก", "ดาวน์โหลด", "ออกรายงาน", "ออกไฟล์", "สร้างรายงาน",
    "โหลด", "โหลดได้", "ขอโหลด", "บันทึก", "save", "ไฟล์",
    "export", "download", "report", "excel", "xlsx",
]

def _is_report_request(question: str) -> bool:
    q = question.lower()
    return any(kw in q for kw in _REPORT_KEYWORDS)


def _save_report(df: pd.DataFrame) -> str:
    # Drop _col-suffixed columns that are merge artifacts (base column already present)
    artifacts = [c for c in df.columns if c.endswith("_col") and c[:-4] in df.columns]
    if artifacts:
        df = df.drop(columns=artifacts)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = REPORTS_DIR / f"report_{ts}.xlsx"
    df.to_excel(path, index=False, engine="openpyxl")
    sess = _get_session()
    sess["last_report_rows"] = len(df)
    sess["last_report_cols"] = len(df.columns)
    return str(path)


def get_report_info() -> dict:
    """Return last-report metadata from the current thread session."""
    sess = _get_session()
    return {
        "file": sess.get("last_report_file"),
        "rows": sess.get("last_report_rows", 0),
        "cols": sess.get("last_report_cols", 0),
    }


# ── Agent loop ────────────────────────────────────────────────────────────────

_AGENT_SYSTEM_TEMPLATE = """\
You are a query orchestrator for a Thai financial portfolio assistant.
Module: {module}  |  Pre-routed table: {table_hint}

Your only job is to decide WHAT to compute and WHICH table to use.
A specialist will write and execute the actual pandas code.

Tools available:
  retrieve_knowledge  -- get domain rules/column definitions from knowledge base (use when unsure)
  generate_and_run    -- describe what to compute; specialist writes + runs the code
  finish              -- call when you have a valid result

Tables for {module}:
{table_desc}

INTENT RULES (read before every generate_and_run call):
- "แสดง / ขอดู / รายชื่อ / list / show / ดู" in the question → intent MUST describe returning ROWS/RECORDS. Do NOT translate to sum, total, or aggregate.
- "กี่คน / กี่รายการ / กี่ราย / จำนวน / how many / นับ" → describe counting/groupby.
- Preserve the exact operation type from the Question. Never upgrade "show rows" to "sum values".

Workflow:
1. Optionally call retrieve_knowledge if you need domain context.
2. Call generate_and_run(intent, table). Be specific in the intent — preserve the operation type from the Question (show rows vs count vs sum).
3. If result is ERROR: call generate_and_run again with the SAME table and the SAME original intent — only fix what the error says (e.g., wrong column name). Do NOT invent a new question or switch intent. Only change table if the error says the entire table is wrong.
4. If result is 0 or empty after a previous ERROR, verify that the current intent still directly answers the user's original question before calling finish. A 0 from the wrong question is NOT a valid answer.
5. Call finish() once satisfied.

Limits: retrieve_knowledge <= 2x, generate_and_run <= 4x.\
"""

_MAX_ITERS = 10


def _run_agent_loop(
    question: str,
    module: str,
    history: list[dict],
    dfs: dict,
    schemas: dict,
    table_hint: str,
    follow_up_context: str,
    periods_info: str,
    rag_context: str,
    is_report: bool = False,
    df_user: "pd.DataFrame | None" = None,
    user_key_col: str = "",
) -> dict:
    table_desc = "\n".join(
        f"  {name}: {desc}" for name, desc in TABLE_DESCRIPTIONS.get(module, {}).items()
    )
    system = _AGENT_SYSTEM_TEMPLATE.format(
        module=module.upper(), table_hint=table_hint, table_desc=table_desc
    )

    if is_report:
        if table_hint == "collection":
            report_hint = (
                "[REPORT MODE: User wants a downloadable Excel export. "
                "Use the collection table (df_coll) — do NOT switch to outstanding or outstandingcol. "
                "Result must be a FULL row-level DataFrame with all relevant columns — do NOT aggregate.]\n\n"
            )
        else:
            report_hint = (
                "[REPORT MODE: User wants a downloadable Excel export. "
                "In your generate_and_run intent, explicitly describe: "
                "(1) which rows to filter, "
                "(2) that the result must be a FULL row-level DataFrame merged from BOTH tables (outstanding + collateral) — do NOT aggregate. "
                "The specialist merges all columns automatically — just describe the filter and the join.]\n\n"
            )
    else:
        report_hint = ""

    first_user = question
    if rag_context:
        first_user = (
            f"Question: {question}\n\n"
            f"[Background context — business rules only. "
            f"Derive your compute intent ONLY from the Question above, NOT from this block:]\n"
            f"{rag_context}"
        )
    if report_hint:
        first_user = f"{report_hint}{first_user}"
    if follow_up_context:
        first_user = f"[{follow_up_context}]\n\n{first_user}"

    messages: list[dict] = []
    # For follow-ups: full history so agent understands the prior result.
    # For fresh questions: only pass the previous question text (not the answer) —
    # the answer contains entity names that prime the agent to echo the wrong company.
    if follow_up_context:
        for h in history[-2:]:
            messages.append({"role": "user", "content": h["question"]})
            messages.append({"role": "assistant", "content": _clean_for_history(h["answer"])})
    else:
        for h in history[-1:]:
            messages.append({"role": "user", "content": h["question"]})
            messages.append({"role": "assistant", "content": "(answered)"})
    messages.append({"role": "user", "content": first_user})

    _log("AGENT START",
         module=module, table_hint=table_hint,
         follow_up=bool(follow_up_context),
         history_turns_passed=len(messages) - 1,
         question=question)

    agent_tools = _get_agent_tools(module)
    tool_trace: list[dict] = []
    last_raw: object = None
    last_code: str = ""
    last_rdf = None
    last_table_used: str = table_hint
    accumulated_rag: str = rag_context  # grows if agent calls retrieve_knowledge
    last_error_hint: str = ""           # passed to codegen on retry after ERROR

    for iteration in range(_MAX_ITERS):
        _log(f"AGENT → LLM (iter {iteration + 1})",
             messages_in_thread=len(messages),
             last_user_msg=next((m["content"] for m in reversed(messages) if m["role"] == "user"), ""))
        resp = _call_llm_with_tools(system, messages, agent_tools, role="agent")
        _log(f"AGENT ← LLM (iter {iteration + 1})",
             finish_reason=resp.finish_reason,
             content=resp.content or "(none)",
             tool_calls=[(tc.name, tc.args) for tc in resp.tool_calls])

        if resp.finish_reason == "stop" or not resp.tool_calls:
            return {
                "type": "analytical",
                "answer": resp.content or "",
                "rag_context": rag_context,
                "tool_trace": tool_trace,
            }

        messages.append({
            "role": "assistant",
            "content": resp.content,
            "_tool_calls": [{"id": tc.id, "name": tc.name, "args": tc.args} for tc in resp.tool_calls],
        })

        done = False
        for tc in resp.tool_calls:
            if tc.name == "finish":
                _log("AGENT TOOL", tool="finish")
                done = True
                break

            elif tc.name == "retrieve_knowledge":
                query = tc.args.get("query", question)
                _log("AGENT TOOL", tool="retrieve_knowledge", query=query)
                rag_result = rag_retrieve(query, n_results=6)
                _log("RAG RESULT", chars=len(rag_result or ""), preview=(rag_result or "")[:300])
                if rag_result:
                    accumulated_rag = f"{accumulated_rag}\n\n---\n\n{rag_result}" if accumulated_rag else rag_result
                tool_trace.append({"tool": "retrieve_knowledge", "query": query})
                messages.append({
                    "role": "tool", "tool_call_id": tc.id,
                    "tool_name": tc.name, "content": rag_result or "(no results)",
                })

            elif tc.name == "generate_and_run":
                intent = tc.args.get("intent", question)
                table = tc.args.get("table", table_hint)
                last_table_used = table

                schema = _get_codegen_schema(table, dfs, schemas, module)
                df_user_schema = get_schema_description(df_user, module=module, table="user_upload") if df_user is not None and len(df_user) > 0 else ""
                code = _generate_code(intent, schema, module, periods_info, follow_up_context, error_hint=last_error_hint, rag_context=accumulated_rag, original_question=question, is_report=is_report, df_user_schema=df_user_schema, user_key_col=user_key_col)
                result_str, raw, rdf = _safe_exec(code, dfs, table, is_report=is_report, df_user=df_user)
                last_raw, last_code, last_rdf = raw, code, rdf
                last_error_hint = result_str[:300] if result_str.startswith("ERROR:") else ""

                _log("EXEC RESULT", table=table, result_type=type(raw).__name__, result_preview=result_str[:400])
                tool_trace.append({
                    "tool": "generate_and_run",
                    "intent": intent, "table": table,
                    "code": code, "result_preview": result_str[:300],
                })

                # Give agent both code and result so it can evaluate quality
                tool_msg = f"Code executed:\n```python\n{code}\n```\n\nResult: {result_str}"
                messages.append({
                    "role": "tool", "tool_call_id": tc.id,
                    "tool_name": tc.name, "content": tool_msg,
                })

        if done:
            break

    return {
        "type": "data_query",
        "raw_result": last_raw,
        "code": last_code,
        "result_df": last_rdf,
        "table_used": last_table_used,
        "rag_context": rag_context,
        "tool_trace": tool_trace,
    }


# ── Output helpers ─────────────────────────────────────────────────────────────

def _strip_cjk(text: str) -> str:
    return "".join(
        ch for ch in text
        if not ('一' <= ch <= '鿿')
        and not ('㐀' <= ch <= '䶿')
        and not ('　' <= ch <= '〿')
        and not ('＀' <= ch <= '￯')
    )


def _extract_code(text: str) -> str:
    if "```python" in text:
        start = text.index("```python") + len("```python")
        end = text.index("```", start)
        return text[start:end].strip()
    if "```" in text:
        start = text.index("```") + 3
        end = text.index("```", start)
        return text[start:end].strip()
    return text.strip()


_BADGE_RE = re.compile(r'\n*-{3,}\n📅[^\n]*', re.MULTILINE)


def _make_period_badge(raw_result: object, result_df: object, is_trend_q: bool) -> str:
    """Compute badge from actual result data. Shows all distinct periods present in the data."""
    if is_trend_q:
        return ""
    for candidate in [result_df, raw_result if isinstance(raw_result, pd.DataFrame) else None]:
        if not isinstance(candidate, pd.DataFrame) or len(candidate) == 0:
            continue
        if 'ปี' not in candidate.columns or 'เดือน' not in candidate.columns:
            continue
        try:
            periods = (candidate[['ปี', 'เดือน']]
                       .drop_duplicates()
                       .sort_values('ปี'))
            labels = [
                f"{_MONTH_THAI.get(str(r['เดือน']), str(r['เดือน']))} {int(r['ปี']) + 543}"
                for _, r in periods.iterrows()
            ]
            return f"\n\n---\n📅 ข้อมูล ณ เดือน{' และ '.join(labels)}"
        except Exception:
            continue
    return ""

def _clean_for_history(answer: str) -> str:
    cleaned = re.sub(r'<details>.*?</details>', '', answer, flags=re.DOTALL)
    cleaned = re.sub(r'💬 \*\*Analysis\*\*\n?', '', cleaned)
    cleaned = _BADGE_RE.sub('', cleaned)
    return cleaned.strip()


def _strip_analysis_header(text: str) -> str:
    return re.sub(
        r'^[\s*_]*(analysis|การวิเคราะห์|summary|สรุป)[\s*_:—-]*',
        '', text, flags=re.IGNORECASE
    ).lstrip()


def _history_messages(history: list[dict]) -> list[dict]:
    msgs = []
    for h in history[-4:]:
        msgs.append({"role": "user", "content": h["question"]})
        msgs.append({"role": "assistant", "content": _clean_for_history(h["answer"])})
    return msgs


_MAX_DISPLAY_ROWS = 100


def _format_raw_display(raw_result: object) -> tuple[str, int]:
    _TABLE_STYLE = 'style="border-collapse:collapse; white-space:nowrap; font-size:0.85em;"'
    _TH_STYLE = 'style="border:1px solid #555; padding:4px 8px; background:#2a2a2a; color:#eee;"'
    _TD_STYLE = 'style="border:1px solid #444; padding:4px 8px;"'

    def _df_to_html(df: pd.DataFrame) -> str:
        def _fmt(v) -> str:
            if isinstance(v, float) and not pd.isna(v) and v == int(v):
                return _html.escape(str(int(v)))
            return _html.escape(str(v))
        headers = "".join(f"<th {_TH_STYLE}>{_html.escape(str(c))}</th>" for c in df.columns)
        rows = "".join(
            f"<tr>{''.join(f'<td {_TD_STYLE}>{_fmt(v)}</td>' for v in row)}</tr>"
            for _, row in df.iterrows()
        )
        return f"<table {_TABLE_STYLE}><thead><tr>{headers}</tr></thead><tbody>{rows}</tbody></table>"

    def _wrap(inner: str, note: str = "") -> str:
        return (
            f'<div style="overflow-x:auto;">{inner}</div>'
            + (f"\n<small><em>{note}</em></small>" if note else "")
        )

    if isinstance(raw_result, pd.DataFrame):
        n = len(raw_result)
        note = f"Showing {_MAX_DISPLAY_ROWS:,} of {n:,} rows" if n > _MAX_DISPLAY_ROWS else ""
        return _wrap(_df_to_html(raw_result.head(_MAX_DISPLAY_ROWS)), note), n
    if isinstance(raw_result, pd.Series):
        n = len(raw_result)
        note = f"Showing {_MAX_DISPLAY_ROWS:,} of {n:,} rows" if n > _MAX_DISPLAY_ROWS else ""
        return _wrap(
            _df_to_html(raw_result.head(_MAX_DISPLAY_ROWS).to_frame(name="value").reset_index()), note
        ), n
    return str(raw_result), 1


_SUMMARY_CELL_LIMIT = 5000
_SKIP_SUM_COLS: set[str] = {"จำนวนทรัพย์หลักประกัน"}


def _build_summary_context(
    raw_result: object, code: str = "", result_df: pd.DataFrame | None = None
) -> str:
    lines = []
    if code:
        lines.append(f"Pandas code:\n```python\n{code}\n```")
    if isinstance(raw_result, pd.DataFrame):
        r, c = len(raw_result), len(raw_result.columns)
        if r * c <= _SUMMARY_CELL_LIMIT:
            lines.append(f"Result ({r} rows x {c} cols -- use ALL values exactly):")
            lines.append(raw_result.to_string(index=False))
        else:
            lines.append(f"EXACT RESULT: {r:,} rows ({c} cols). Report verbatim.")
            for col in raw_result.select_dtypes(include="number").columns:
                if col in _SKIP_SUM_COLS:
                    continue
                s = raw_result[col]
                lines.append(f"  {col}: sum={s.sum():,.0f} mean={s.mean():,.0f} min={s.min():,.0f} max={s.max():,.0f}")
            for col in raw_result.select_dtypes(exclude="number").columns[:3]:
                lines.append(f"  {col} top values: {raw_result[col].value_counts().head(10).to_dict()}")
    elif isinstance(raw_result, pd.Series):
        n = len(raw_result)
        if n <= _SUMMARY_CELL_LIMIT:
            lines.append(f"Result ({n} entries -- use ALL values exactly):")
            lines.append(raw_result.to_string())
        else:
            lines.append(f"EXACT RESULT: {n:,} entries. Top 20:")
            lines.append(raw_result.head(20).to_string())
            lines.append(f"... ({n - 20:,} more)")
    else:
        lines.append(f"Result: {raw_result}")
        if result_df is not None and isinstance(result_df, pd.DataFrame) and len(result_df) > 0:
            rdf_cells = len(result_df) * len(result_df.columns)
            if rdf_cells <= _SUMMARY_CELL_LIMIT:
                lines.append(f"\nBreakdown ({len(result_df)} rows -- exact values):")
                lines.append(result_df.to_string(index=False))
            else:
                lines.append(f"\nBreakdown: {len(result_df):,} rows")
                for col in result_df.select_dtypes(include="number").columns:
                    if col in _SKIP_SUM_COLS:
                        continue
                    s = result_df[col]
                    lines.append(f"  {col}: sum={s.sum():,.0f} mean={s.mean():,.0f}")
    return "\n".join(lines)


# ── Clarification generator ────────────────────────────────────────────────────

def _clarify_stream(question: str, module: str):
    """Ask the user a contextual clarification question in Thai.
    Table list and descriptions come from TABLE_REGISTRY — never hardcoded."""
    module_desc = _TABLE_THAI_DESC.get(module, {})
    table_lines = "\n".join(
        f"  • {module_desc.get(t, t)}"
        for t in get_tables(module)
    )
    system = (
        f"คุณเป็นผู้ช่วยข้อมูลการเงินของสถาบันการเงินไทย โมดูล: {module.upper()}\n"
        f"คำถามของผู้ใช้ไม่ชัดเจนพอที่จะดำเนินการได้\n\n"
        f"ให้สร้างคำถามกลับเพื่อขอข้อมูลเพิ่มเติม โดย:\n"
        f"- แสดงว่าระบบไม่แน่ใจว่าต้องการอะไร\n"
        f"- แสดงรายการข้อมูลที่มีในโมดูลนี้ให้ผู้ใช้เลือก\n"
        f"- อย่าตอบคำถาม อย่าสร้างข้อมูลขึ้นมาเอง\n"
        f"- เป็นกันเอง สั้นกระชับ ไม่เกิน 6 บรรทัด\n\n"
        f"ข้อมูลที่มีใน {module.upper()}:\n{table_lines}\n\n"
        f"ตอบเป็นภาษาไทยเท่านั้น"
    )
    messages = [{"role": "user", "content": question}]
    for chunk in _call_llm_stream(system, messages, temperature=0.3, role="summarize"):
        yield _strip_cjk(chunk)


# ── Summary + analyst systems ──────────────────────────────────────────────────

_SUMMARY_SYSTEM_BASE = """\
You are a senior portfolio analyst at a Thai financial institution. Currency: Thai Baht. Never use $.

CRITICAL rules:
- NEVER change any number -- copy exactly as shown.
- NEVER fabricate statistics not in the result.
- Scalar result: state the number clearly in Thai with its natural unit from the question (คน / รายการ / บาท). If breakdown data is provided below the result, add 2-3 factual lines from it (e.g., ยอดหนี้รวม, มูลค่าหลักประกันรวม). NEVER fabricate statistics not in the provided data.
- DataFrame result: state row count, describe what is shown. Do NOT sum/average columns.
- NEVER sum 'จำนวนทรัพย์หลักประกัน' -- pre-computed, summing is meaningless.
- "แสดง/show/list" queries: row count + 2-3 notable observations only.
- Reply in same language as user (Thai or English). Never mix in Chinese.
- Answer directly -- finding first, then brief insight. No preamble or headers.
- End your response with one short line stating the temporal scope of the data in natural Thai: which snapshot date, purchase period, or date range the result covers. Examples: "ข้อมูล ณ เดือนมีนาคม 2569" / "กรองเฉพาะลูกหนี้ที่ซื้อมาในปี 2568" / "เปรียบเทียบข้อมูล ธันวาคม 2568 กับ มีนาคม 2569". Use Thai Buddhist year (ปี+543).\
"""
_SUMMARY_MODULE_NPL = "\nModule: NPL -- ภาระหนี้คงเหลือ=debt(HIGH=BAD), มูลค่าหลักประกัน=collateral(HIGH=GOOD). Groups: 01=ประนอมหนี้ 02=ยังไม่ดำเนินคดี 03=ดำเนินคดี 04=บังคับคดี 05=รอขายทอดตลาด 06=ล้มละลาย 07=ตัดหนี้สูญ.\n"
_SUMMARY_MODULE_NPA = "\nModule: NPA -- each record is an asset (NOT a debtor). Use ทรัพย์/asset language. ราคาประเมิน=appraisal, ราคาตั้งขาย=asking price, ต้นทุนรวม=cost, ระยะเวลาถือครอง NPA (ปี)=holding years.\n"

_ANALYST_SYSTEM_BASE = """\
You are a senior portfolio analyst and strategist at a Thai financial institution. Currency: Thai Baht.

CRITICAL RULES:
- NEVER fabricate numbers. You have NO access to the database.
- NEVER write code. If asked for actual numbers without data in history, say to rephrase as a data question.
- Only use numbers that appear explicitly in conversation history.
- NEVER fabricate debtor records, debtor IDs, names, amounts, or any example rows.
  If the user asks for "N ตัวอย่าง / N ราย / ขอตัวอย่าง", respond:
  "กรุณาถามใหม่เป็นคำถามข้อมูล เช่น 'แสดงลูกหนี้ Non-TDR ที่มีหลักประกัน 10 รายแรก'
   เพื่อให้ระบบดึงข้อมูลจริงจากฐานข้อมูลแทนการสร้างตัวอย่างขึ้นมาเอง"

Answer strategic/analytical questions using history and financial domain knowledge.
Reply in same language as user. Be specific and insightful.\
"""
_ANALYST_MODULE_NPL = "\nModule: NPL -- ภาระหนี้คงเหลือ(HIGH=BAD), มูลค่าหลักประกัน(HIGH=GOOD). TDR=restructured. Groups: 01-07.\n"
_ANALYST_MODULE_NPA = "\nModule: NPA -- asset/property portfolio. ราคาประเมิน=appraisal, ระยะเวลาถือครอง=holding period. Focus: disposal strategy, margin analysis.\n"


def _get_summary_system(module: str) -> str:
    return _SUMMARY_SYSTEM_BASE + (_SUMMARY_MODULE_NPA if module == "npa" else _SUMMARY_MODULE_NPL)


def _get_analyst_system(module: str) -> str:
    return _ANALYST_SYSTEM_BASE + (_ANALYST_MODULE_NPA if module == "npa" else _ANALYST_MODULE_NPL)


def _build_analyst_schema_block(schema: str) -> str:
    cols = re.findall(r"^\s*'([^']+)':", schema, re.MULTILINE)
    if not cols:
        return ""
    return "\nAvailable columns (reference only -- do NOT fabricate values):\n" + ", ".join(f"'{c}'" for c in cols)


def _summarize_stream(
    question: str, raw_result: object, code: str, history: list[dict],
    rag_context: str = "", module: str = "npl", result_df: pd.DataFrame | None = None,
):
    context = _build_summary_context(raw_result, code=code, result_df=result_df)
    rag_block = f"\n\nRelevant knowledge:\n{rag_context}" if rag_context else ""
    messages = _history_messages(history[-2:])
    messages.append({"role": "user", "content": f"Question: {question}\n\nQuery result:\n{context}"})
    _log("SUMMARIZE → LLM", question=question, result_type=type(raw_result).__name__, context=context)
    first, buffer = True, ""
    for chunk in _call_llm_stream(_get_summary_system(module) + rag_block, messages, temperature=0.3, role="summarize"):
        chunk = _strip_cjk(chunk)
        if first:
            buffer += chunk
            if len(buffer) >= 30:
                buffer = _strip_analysis_header(buffer)
                yield buffer
                buffer = ""
                first = False
        else:
            yield chunk
    if buffer:
        yield _strip_analysis_header(buffer)


def _analyze_stream(
    question: str, schema: str, history: list[dict], rag_context: str = "", module: str = "npl"
):
    schema_block = _build_analyst_schema_block(schema)
    rag_block = f"\n\nRelevant knowledge:\n{rag_context}" if rag_context else ""
    messages = _history_messages(history)
    messages.append({"role": "user", "content": question})
    for chunk in _call_llm_stream(_get_analyst_system(module) + schema_block + rag_block, messages, temperature=0.4, role="summarize"):
        yield _strip_cjk(chunk)


# ── Plotly chart generation ────────────────────────────────────────────────────

def _try_make_chart(raw_result: object, question: str) -> str:
    """Return plotly HTML for groupby/trend results. Empty string if not applicable."""
    try:
        import plotly.express as px
        import plotly.io as pio

        if isinstance(raw_result, pd.Series) and 1 < len(raw_result) <= 50:
            title = question[:60]
            df_chart = raw_result.reset_index()
            df_chart.columns = [str(c) for c in df_chart.columns]
            x_col, y_col = df_chart.columns[0], df_chart.columns[1]
            fig = px.bar(df_chart, x=x_col, y=y_col, title=title,
                         template="plotly_dark", height=350)
            fig.update_layout(margin=dict(l=20, r=20, t=40, b=20))
            return pio.to_html(fig, include_plotlyjs="cdn", full_html=False)

        if isinstance(raw_result, pd.DataFrame) and len(raw_result.columns) == 2 and 1 < len(raw_result) <= 50:
            df_chart = raw_result.copy()
            df_chart.columns = [str(c) for c in df_chart.columns]
            x_col, y_col = df_chart.columns[0], df_chart.columns[1]
            if pd.api.types.is_numeric_dtype(df_chart[y_col]):
                fig = px.bar(df_chart, x=x_col, y=y_col, title=question[:60],
                             template="plotly_dark", height=350)
                fig.update_layout(margin=dict(l=20, r=20, t=40, b=20))
                return pio.to_html(fig, include_plotlyjs="cdn", full_html=False)
    except Exception:
        pass
    return ""


# ── Reasoning accordion ────────────────────────────────────────────────────────

def _build_reasoning_accordion(
    tool_trace: list[dict], rag_context: str, qtype: str = "data_query",
    table_hint: str = "", classify_provider: str = "", agent_provider: str = "",
) -> str:
    classify_info = f"`{classify_provider}`" if classify_provider else f"`{_resolve_provider('classify')}`"
    agent_info = f"`{agent_provider}`" if agent_provider else f"`{_resolve_provider('agent')}`"
    codegen_info = f"`{_resolve_provider('codegen')}`"
    summarize_info = f"`{_resolve_provider('summarize')}`"

    lines = [
        f"**Architecture:** 3.0 -- classify / pre-route / agent / specialist codegen / stream",
        f"**Classify model:** {classify_info}  |  **Agent:** {agent_info}  |  "
        f"**Code-gen:** {codegen_info}  |  **Summary:** {summarize_info}",
        f"**Type:** `{qtype}`" + (f"  |  **Pre-routed table:** `{table_hint}`" if table_hint else ""),
        "",
    ]

    if rag_context:
        lines.append("**Initial RAG context:**")
        for chunk in rag_context.split("\n\n---\n\n"):
            first_line = chunk.strip().split("\n")[0]
            preview = " ".join(chunk.strip().split("\n")[1:4])[:180]
            lines.append(f"- {first_line}: {preview}...")
        lines.append("")

    for i, step in enumerate(tool_trace, 1):
        if step["tool"] == "retrieve_knowledge":
            lines.append(f"**Step {i} -- retrieve_knowledge:** `{step['query']}`")
        elif step["tool"] == "generate_and_run":
            lines.append(f"**Step {i} -- generate_and_run** (table=`{step['table']}`):")
            lines.append(f"Intent: _{step['intent']}_")
            lines.append(f"Result preview: `{step['result_preview']}`")
            lines.append(f"```python\n{step['code']}\n```")

    body = "\n".join(lines)
    return f"<details>\n<summary>🔬 3.0 Reasoning &nbsp;▼</summary>\n\n{body}\n\n</details>"


# ── Main entry point ───────────────────────────────────────────────────────────

def run_query(question: str, module: str, history: list[dict], df_user: "pd.DataFrame | None" = None, user_key_col: str = ""):
    """Generator -- yields str for each streaming update.
    Final yield may be a (str, file_path) tuple when the request produced a report file."""
    _log("RUN QUERY", question=question, module=module, history_turns=len(history))
    rag_set_module(module)

    is_report = _is_report_request(question)
    _get_session()["last_report_file"] = None  # reset every turn

    # Load all tables (cached after first call)
    dfs: dict[str, pd.DataFrame] = {}
    schemas: dict[str, str] = {}
    for table in get_tables(module):
        dfs[table] = load_table(module, table)
        schemas[table] = get_schema_description(dfs[table], module, table)

    # Dynamic periods info
    try:
        _out = dfs.get("outstanding", pd.DataFrame())
        _pdf = _out[['ปี', 'เดือน']].drop_duplicates().sort_values(['ปี', 'เดือน'])
        _strs = [f"(ปี={int(r['ปี'])}, เดือน='{r['เดือน']}')" for _, r in _pdf.iterrows()]
        periods_info = f"Periods: {', '.join(_strs)}. Latest: {_strs[-1]}." if _strs else ""
    except Exception:
        periods_info = ""


    # Step 1: RAG + classify
    rag_context = rag_retrieve(question, n_results=6)
    _log("RAG (initial)", question=question, chunks_returned=rag_context.count("---") + 1 if rag_context else 0, preview=rag_context[:400] if rag_context else "(none)")
    try:
        qtype = _classify(question, history, rag_context, module)
    except RuntimeError as e:
        yield f"**API Error (classify):** {e}"
        return

    # Report requests always require a data pull — override any misclassification
    if is_report and qtype != "out_of_scope":
        qtype = "data_query"

    # Step 2: Out of scope
    if qtype == "out_of_scope":
        reasoning = _build_reasoning_accordion([], rag_context, qtype="out_of_scope") if SHOW_REASONING else ""
        msg = "ขออภัย -- ฉันตอบได้เฉพาะคำถามเกี่ยวกับพอร์ตสินทรัพย์ (NPL/NPA) เท่านั้น"
        yield f"{reasoning}\n\n{msg}" if reasoning else msg
        return

    # Step 2.5: Clarification needed — question too vague to execute
    if qtype == "clarification":
        reasoning = _build_reasoning_accordion([], rag_context, qtype="clarification") if SHOW_REASONING else ""
        prefix = f"{reasoning}\n\n" if reasoning else ""
        accumulated = ""
        for chunk in _clarify_stream(question, module):
            accumulated += chunk
            yield f"{prefix}{accumulated}"
        return

    # Pre-compute session + follow-up detection (shared by mixed + data_query)
    _sess = _get_session()
    _DISPLAY_ONLY_PAT = re.compile(
        r'^(?:ขอดู|แสดง|show|list|ดู)\s*\d+\s*(?:รายแรก|ราย|อันดับ|แถว|row|record)?',
        re.IGNORECASE,
    )
    _TABLE_OVERRIDE_KWS = [
        "ผลเรียกเก็บ", "cash", "lgo1", "หลักประกัน", "จังหวัด", "ไร่", "โฉนด",
        "เงินรับ", "เก็บได้", "tdr", "ประนอมหนี้",
    ]
    # LLM-based follow-up detection — only runs when a previous result exists in session
    _is_followup = False
    if _sess.get("last_debtor_ids") and history:
        _is_followup = _classify_followup(question, history[-1]["question"])

    # Step 3: Analytical -- stream directly, skip agent entirely
    if qtype == "analytical":
        reasoning = _build_reasoning_accordion([], rag_context, qtype="analytical") if SHOW_REASONING else ""
        prefix = f"{reasoning}\n\n" if reasoning else ""
        accumulated = ""
        # Pass all table schemas so the analyst knows every table (not just outstanding)
        schema = "\n\n---\n\n".join(f"[TABLE: {t}]\n{s}" for t, s in schemas.items())
        for chunk in _analyze_stream(question, schema, history, rag_context, module):
            accumulated += chunk
            yield f"{prefix}{accumulated}"
        return

    # Step 3.5: Mixed -- analyst reasons about criteria first, agent pulls real matching data
    if qtype == "mixed":
        _is_df = (
            bool(_DISPLAY_ONLY_PAT.search(question.strip()))
            and not any(kw in question.lower() for kw in _TABLE_OVERRIDE_KWS)
            and bool(_sess.get("last_table"))
        )
        if _is_df or (_is_followup and not any(kw in question.lower() for kw in _TABLE_OVERRIDE_KWS)):
            table_choice = _sess["last_table"]
        else:
            pre = _pre_route(question, module, history)
            _log("PRE-ROUTE (mixed)", result=pre or "None → LLM router")
            try:
                table_choice = pre or _route_table(question, module, history, rag_context)
            except RuntimeError as e:
                yield f"**API Error (routing):** {e}"
                return

        follow_up_context = _build_followup_context(module) if _is_followup else ""

        # Preliminary reasoning (no tool_trace yet — rebuilt after agent finishes)
        pre_reasoning = (
            _build_reasoning_accordion([], rag_context, "mixed", table_choice)
            if SHOW_REASONING else ""
        )
        pre_prefix = f"{pre_reasoning}\n\n" if pre_reasoning else ""

        # Step A: Stream analyst reasoning so user sees criteria immediately
        analysis_header = "🔍 **Analysis & Criteria**\n"
        analysis_text = ""
        schema = "\n\n---\n\n".join(f"[TABLE: {t}]\n{s}" for t, s in schemas.items())
        for chunk in _analyze_stream(question, schema, history, rag_context, module):
            analysis_text += chunk
            yield f"{pre_prefix}{analysis_header}{analysis_text}"

        # Bridge: signal transition to data pull
        yield f"{pre_prefix}{analysis_header}{analysis_text}\n\n---\n\n⏳ กำลังดึงข้อมูลจริงจากฐานข้อมูล..."

        # Step B: Agent loop — analyst output becomes the query plan
        agent_question = (
            f"[Analyst strategy and criteria:]\n{analysis_text[:1500]}\n\n"
            f"[User request:]\n{question}\n\n"
            f"Execute a data query matching the criteria above. Return real records from the database."
        )
        try:
            result = _run_agent_loop(
                agent_question, module, history, dfs, schemas,
                table_hint=table_choice,
                follow_up_context=follow_up_context,
                periods_info=periods_info,
                rag_context=rag_context,
                is_report=is_report,
                df_user=df_user,
                user_key_col=user_key_col,
            )
        except RuntimeError as e:
            yield f"{pre_prefix}{analysis_header}{analysis_text}\n\n**API Error (agent):** {e}"
            return
        except Exception as e:
            yield f"{pre_prefix}{analysis_header}{analysis_text}\n\n**Unexpected error:** {e}"
            return

        _update_session(result, module, table_choice)
        rag_ctx_m  = result.get("rag_context", rag_context)
        tool_trace_m = result.get("tool_trace", [])
        reasoning_m = (
            _build_reasoning_accordion(tool_trace_m, rag_ctx_m, "mixed", table_choice)
            if SHOW_REASONING else ""
        )

        # Edge case: agent answered analytically without tools
        if result["type"] == "analytical":
            txt = _strip_cjk(result.get("answer", ""))
            parts = [reasoning_m, analysis_header + analysis_text, "---", txt]
            yield "\n\n".join(p for p in parts if p)
            return

        raw_m = result.get("raw_result")
        code_m = result.get("code", "")
        rdf_m  = result.get("result_df")

        if raw_m is None:
            yield f"{reasoning_m}\n\n{analysis_header}{analysis_text}\n\nAgent did not produce data. กรุณาลองใหม่"
            return

        if isinstance(raw_m, pd.DataFrame) and len(raw_m) == 0:
            yield (
                f"{reasoning_m}\n\n{analysis_header}{analysis_text}\n\n"
                "ไม่พบข้อมูลที่ตรงกับเงื่อนไขนี้ (0 รายการ)"
            )
            return

        chart_m = _try_make_chart(raw_m, question)

        is_df_m  = isinstance(raw_m, pd.DataFrame)
        is_ser_m = isinstance(raw_m, pd.Series)
        has_lst_m = not is_df_m and not is_ser_m and isinstance(rdf_m, pd.DataFrame) and len(rdf_m) > 0
        if has_lst_m:
            _idc = "รหัสลูกหนี้" if module == "npl" else "รหัสตลาด"
            _rdf_m = rdf_m.drop_duplicates(subset=[_idc]) if _idc in rdf_m.columns else rdf_m
        else:
            _rdf_m = None
        disp_m = raw_m if (is_df_m or is_ser_m) else (_rdf_m if has_lst_m else None)

        accordion_m = ""
        if disp_m is not None:
            dhtml_m, rcnt_m = _format_raw_display(disp_m)
            accordion_m = (
                f"<details>\n<summary>📊 Raw Data -- {rcnt_m:,} row(s) &nbsp;▼</summary>\n\n"
                f"{dhtml_m}\n\n</details>"
            )

        summary_header = "💬 **Summary**\n"
        base_m = f"{reasoning_m}\n\n{analysis_header}{analysis_text}\n\n---\n\n"
        summ_m = ""
        for chunk in _summarize_stream(question, raw_m, code_m, history, rag_ctx_m, module, rdf_m):
            summ_m += chunk
            yield f"{base_m}{summary_header}{summ_m}"

        final_m = [reasoning_m, analysis_header + analysis_text, "---"]
        if chart_m:
            final_m.append(chart_m)
        if accordion_m:
            final_m.append(accordion_m)
        final_m.append(summary_header + summ_m)
        final_text_m = "\n\n".join(p for p in final_m if p)
        report_file_m = _get_session().get("last_report_file")
        if report_file_m:
            yield final_text_m, report_file_m
        else:
            yield final_text_m
        return

    # Step 4: Pre-route (data_query)
    _is_display_followup = (
        bool(_DISPLAY_ONLY_PAT.search(question.strip()))
        and not any(kw in question.lower() for kw in _TABLE_OVERRIDE_KWS)
        and bool(_sess.get("last_table"))
    )
    if _is_display_followup or (_is_followup and not any(kw in question.lower() for kw in _TABLE_OVERRIDE_KWS)):
        table_choice = _sess["last_table"]
    else:
        pre = _pre_route(question, module, history)
        _log("PRE-ROUTE (data_query)", result=pre or "None → LLM router")
        try:
            table_choice = pre or _route_table(question, module, history, rag_context)
        except RuntimeError as e:
            yield f"**API Error (routing):** {e}"
            return

    _log("TABLE CHOSEN", table=table_choice)

    # Step 5: Follow-up context from session IDs
    follow_up_context = _build_followup_context(module) if _is_followup else ""

    # Step 5.5: Short-circuit — export previous result without re-querying the agent
    if is_report and _is_followup:
        _prev_raw = _sess.get("last_raw_result")
        if isinstance(_prev_raw, pd.DataFrame) and len(_prev_raw) > 0:
            report_path = _save_report(_prev_raw)
            _get_session()["last_report_file"] = report_path
            info = get_report_info()
            reasoning = (
                _build_reasoning_accordion([], rag_context, qtype, table_choice)
                if SHOW_REASONING else ""
            )
            final_text = (
                f"{reasoning}\n\n" if reasoning else ""
            ) + f"ส่งออกข้อมูล {len(_prev_raw):,} รายการ ({info['cols']} คอลัมน์) เป็นไฟล์ Excel เรียบร้อยแล้ว"
            yield final_text, report_path
            return

    # Step 6: Agent loop with progress streaming
    yield f"🤔 Routing to `{table_choice}` -- agent reasoning..."

    try:
        result = _run_agent_loop(
            question, module, history, dfs, schemas,
            table_hint=table_choice,
            follow_up_context=follow_up_context,
            periods_info=periods_info,
            rag_context=rag_context,
            is_report=is_report,
            df_user=df_user,
            user_key_col=user_key_col,
        )
    except RuntimeError as e:
        yield f"**API Error (agent):** {e}\n\nกรุณาลองใหม่หรือเปลี่ยน provider"
        return
    except Exception as e:
        yield f"**Unexpected error:** {e}"
        return

    # Step 7: Update session with result IDs
    _update_session(result, module, table_choice)

    rag_ctx = result.get("rag_context", rag_context)
    tool_trace = result.get("tool_trace", [])
    table_used = result.get("table_used", table_choice)
    reasoning = (
        _build_reasoning_accordion(tool_trace, rag_ctx, qtype, table_choice)
        if SHOW_REASONING else ""
    )

    # Analytical answer from agent (edge case -- agent answered without tools)
    if result["type"] == "analytical":
        answer = _strip_cjk(result.get("answer", ""))
        yield f"{reasoning}\n\n{answer}" if reasoning else answer
        return

    raw_result = result.get("raw_result")
    code = result.get("code", "")
    result_df = result.get("result_df")

    if raw_result is None:
        msg = "Agent did not produce a result. Please try rephrasing your question."
        yield f"{reasoning}\n\n{msg}" if reasoning else msg
        return

    # Empty DataFrame
    if isinstance(raw_result, pd.DataFrame) and len(raw_result) == 0:
        entity = "ทรัพย์" if module == "npa" else "ลูกหนี้"
        prefix = f"{reasoning}\n\n" if reasoning else ""
        yield (
            f"{prefix}ไม่พบข้อมูลที่ตรงกับเงื่อนไขนี้ (0 รายการ)\n\n"
            f"อาจเกิดจาก:\n- ค่าตัวกรองไม่ตรงกับข้อมูล\n"
            f"- ไม่มี{entity}ที่ผ่านเงื่อนไขทั้งหมด\n- กรุณาลองกำหนดเงื่อนไขใหม่"
        )
        return

    # Build chart (groupby/trend results)
    chart_html = _try_make_chart(raw_result, question)

    # Build data accordion
    is_df = isinstance(raw_result, pd.DataFrame)
    is_series = isinstance(raw_result, pd.Series)
    has_list = not is_df and not is_series and isinstance(result_df, pd.DataFrame) and len(result_df) > 0
    if has_list:
        # Deduplicate by ID column — multi-period data causes one debtor to appear per period
        _id_col = "รหัสลูกหนี้" if module == "npl" else "รหัสตลาด"
        _rdf = result_df.drop_duplicates(subset=[_id_col]) if _id_col in result_df.columns else result_df
    else:
        _rdf = None
    display_target = raw_result if (is_df or is_series) else (_rdf if has_list else None)

    data_accordion = ""
    if display_target is not None:
        display_html, row_count = _format_raw_display(display_target)
        data_accordion = (
            f"<details>\n<summary>📊 Raw Data -- {row_count:,} row(s) &nbsp;▼</summary>\n\n"
            f"{display_html}\n\n</details>"
        )

    # Stream analysis
    analysis_header = "💬 **Analysis**\n"
    stream_prefix = f"{reasoning}\n\n{analysis_header}"
    accumulated = ""
    for chunk in _summarize_stream(question, raw_result, code, history, rag_ctx, module, result_df):
        accumulated += chunk
        yield f"{stream_prefix}{accumulated}"

    # Final yield: chart + raw data above analysis
    final_parts = [reasoning]
    if chart_html:
        final_parts.append(chart_html)
    if data_accordion:
        final_parts.append(data_accordion)
    final_parts.append(analysis_header + accumulated)
    final_text = "\n\n".join(p for p in final_parts if p)
    report_file = _get_session().get("last_report_file")
    if report_file:
        yield final_text, report_file
    else:
        yield final_text
