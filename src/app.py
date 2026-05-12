import sys
import os
import time
import traceback

sys.path.insert(0, os.path.dirname(__file__))

import gradio as gr
from pathlib import Path
from data_loader import load_table, get_modules, TABLE_REGISTRY
from query_engine import run_query, PROVIDERS, DEFAULT_PROVIDER, set_provider, get_report_info
from rag_retriever import set_module as rag_set_module
from template_manager import (
    load_templates, save_template, delete_template, update_run,
    load_history, append_history,
)

DEFAULT_MODULE = "npl"
CHAT_HEIGHT    = 640

# Pre-load tables so first query is instant
for _mod, _tables in TABLE_REGISTRY.items():
    for _tbl in _tables:
        print(f"Pre-loading {_mod}/{_tbl}...")
        load_table(_mod, _tbl)
print("Ready.")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(item.get("text", "") for item in content if isinstance(item, dict))
    return str(content)


def _template_choices(templates: list[dict]) -> list[str]:
    return [f"{t['name']}  [{t['module']}]" for t in templates]


def _find_template(label: str, templates: list[dict]) -> dict | None:
    choices = _template_choices(templates)
    idx = choices.index(label) if label in choices else -1
    return templates[idx] if idx >= 0 else None



# ── Chat logic ─────────────────────────────────────────────────────────────────

_STREAM_INTERVAL = 0.08   # seconds between chatbot UI refreshes during streaming


def extract_user_df(file):
    """Parse uploaded Excel/CSV into (DataFrame, key_col_name, status_message).
    Detects the most likely join key column (contains รหัส/id/code).
    Returns (None, "", error_msg) on failure."""
    import pandas as pd
    if file is None:
        return None, "", ""
    try:
        path = file if isinstance(file, str) else file.name
        p = Path(path)
        if p.suffix.lower() in (".xlsx", ".xls"):
            df = pd.read_excel(path)
        else:
            df = pd.read_csv(path, encoding="utf-8-sig")
        if df.empty:
            return None, "", "File is empty."
        # Detect key column: prefer column whose name contains รหัส / id / code
        key_col = ""
        for col in df.columns:
            c = str(col).lower()
            if "รหัส" in c or c in ("id", "code") or "id" in c:
                key_col = col
                break
        if not key_col:
            key_col = df.columns[0]
        # Force key col to string, strip .0 from numeric Excel cells
        df[key_col] = df[key_col].where(
            df[key_col].isna(),
            df[key_col].astype(str).str.replace(r"\.0$", "", regex=True).str.strip(),
        )
        msg = f"Loaded **{len(df):,} rows** from `{p.name}` — join key: `{key_col}`"
        return df, key_col, msg
    except Exception as exc:
        return None, "", f"Error reading file: {exc}"


def respond(message, chatbot_history, our_history, model, module, df_user, user_key_col):
    """Generator — 6 outputs: chatbot, msg_tb, our_history_st,
    report_action_row, report_dl_btn, last_question_st."""
    if not message.strip():
        yield chatbot_history, "", our_history, gr.update(visible=False), gr.update(value=None), ""
        return

    module_l = (module or "npl").lower()
    set_provider(model)
    rag_set_module(module_l)

    display = chatbot_history + [{"role": "user", "content": message}]

    # Yield 1: show user message + "thinking" placeholder immediately, clear input.
    # This prevents the UI feeling frozen during the classify/RAG/routing phase.
    yield (
        display + [{"role": "assistant", "content": "..."}],
        "", our_history,
        gr.update(visible=False), gr.update(value=None),
        message,
    )

    partial = ""
    report_path = None
    last_yield_t = time.time()

    try:
        for val in run_query(message, module_l, our_history, df_user=df_user, user_key_col=user_key_col):
            if isinstance(val, tuple):
                partial, report_path = val[0], val[1]
            else:
                partial = val
            # Throttle: only push a UI update every _STREAM_INTERVAL seconds.
            # Avoids flooding Gradio with hundreds of re-renders for fast token streams.
            now = time.time()
            if now - last_yield_t >= _STREAM_INTERVAL:
                yield (
                    display + [{"role": "assistant", "content": partial}],
                    gr.update(), our_history,
                    gr.update(), gr.update(),
                    message,
                )
                last_yield_t = now
    except Exception as exc:
        traceback.print_exc()
        partial = f"[Error] {exc}"
        report_path = None

    # Final yield: commit history state + show/hide report actions
    final_display   = display + [{"role": "assistant", "content": partial}]
    new_our_history = our_history + [{"question": message, "answer": partial}]

    if report_path:
        info = get_report_info()
        append_history(report_path, message, module_l, info["rows"], info["cols"])
        yield (
            final_display, "", new_our_history,
            gr.update(visible=True),
            gr.update(value=report_path),
            message,
        )
    else:
        yield (
            final_display, "", new_our_history,
            gr.update(visible=False), gr.update(value=None),
            message,
        )


# ── Excel column import ────────────────────────────────────────────────────────

def import_excel_columns(file, current_prompt):
    if file is None:
        return gr.update(), gr.update(value="No file selected.", visible=True)
    try:
        import pandas as pd
        path = file if isinstance(file, str) else file.name
        df   = pd.read_excel(path, nrows=0)
        cols = [c for c in df.columns if not str(c).startswith("Unnamed")]
        if not cols:
            return gr.update(), gr.update(value="No columns found in file.", visible=True)
        col_line = "คอลัมน์ที่ต้องการ: " + ", ".join(str(c) for c in cols)
        existing = (current_prompt or "").strip()
        new_value = f"{existing}\n{col_line}" if existing else col_line
        return gr.update(value=new_value), gr.update(value=f"Imported {len(cols)} columns.", visible=True)
    except Exception as exc:
        return (
            gr.update(value=f"{(current_prompt or '').strip()}\n(อ่านไฟล์ไม่ได้: {exc})".strip()),
            gr.update(value=f"Error: {exc}", visible=True),
        )


# ── Template panel helpers ─────────────────────────────────────────────────────

def refresh_templates():
    templates = load_templates()
    choices   = _template_choices(templates)
    return gr.update(choices=choices, value=None), templates, ""


def on_template_select(label, templates):
    tpl = _find_template(label, templates) if label else None
    if not tpl:
        return ""
    desc     = tpl.get("description") or ""
    runs     = tpl.get("run_count", 0)
    last_run = tpl.get("last_run", "")
    last_run = last_run[:16].replace("T", " ") if last_run else "Never"
    return f"**{tpl['name']}** — *{tpl['module']}*\n\n{desc}\n\n*Runs: {runs} · Last: {last_run}*"


def load_template_prompt(label, templates):
    tpl = _find_template(label, templates) if label else None
    if not tpl:
        return "", DEFAULT_MODULE.upper()
    update_run(tpl["id"])
    desc   = (tpl.get("description") or "").strip()
    prompt = (tpl.get("prompt") or "").strip()
    query  = f"{desc}\n\n{prompt}" if desc and prompt else (desc or prompt)
    return query, tpl["module"]


def do_delete_template(label, templates):
    tpl = _find_template(label, templates) if label else None
    if not tpl:
        return gr.update(), templates, "Select a template first."
    delete_template(tpl["id"])
    new_tpls   = load_templates()
    new_choices = _template_choices(new_tpls)
    return gr.update(choices=new_choices, value=None), new_tpls, f"Deleted: **{tpl['name']}**"


def do_save_template(name, module, desc, prompt, templates):
    if not name.strip() or not prompt.strip():
        gr.Info("Name and Prompt are required.")
        return gr.update(), templates, "Name and prompt are required.", gr.update()
    save_template(name.strip(), module, desc.strip(), prompt.strip())
    new_tpls    = load_templates()
    new_choices = _template_choices(new_tpls)
    gr.Info(f"Saved: {name.strip()}")
    return gr.update(choices=new_choices, value=None), new_tpls, f"Saved: **{name.strip()}**", gr.update(open=False)


def prefill_save_as(last_question, module):
    return (
        gr.update(visible=True),  # open the side panel
        True,                      # panel_visible_st
        gr.update(open=True),     # open the New Template accordion
        "",                        # name — blank, user fills
        module or "NPL",           # module — pre-filled
        "",                        # description — blank
        last_question,             # prompt — pre-filled with last question
    )


# ── History panel helpers ──────────────────────────────────────────────────────

def _history_choices(rev_history: list[dict]) -> list[str]:
    choices = []
    for h in rev_history:
        ts  = h["timestamp"][:16].replace("T", " ")
        q   = h["question"][:35] + "…" if len(h["question"]) > 35 else h["question"]
        choices.append(f"{ts} | {h['module']} | {h.get('rows', 0)} rows | {q}")
    return choices


def refresh_history():
    history = load_history()
    rev     = list(reversed(history))
    return gr.update(choices=_history_choices(rev), value=None), rev


def on_history_change(selected, hist_records):  # inputs order: history_dd, hist_records_st
    if not selected or not hist_records:
        return gr.update(value=None)
    choices = _history_choices(hist_records)
    try:
        idx = choices.index(selected)
        fp  = hist_records[idx].get("file", "")
        if fp and Path(fp).exists():
            return gr.update(value=fp)
    except ValueError:
        pass
    return gr.update(value=None)


# ── UI ─────────────────────────────────────────────────────────────────────────

with gr.Blocks(title="Financial Portfolio Assistant — 3.0") as demo:

    # ── Shared state ──────────────────────────────────────────────────────────
    our_history_st   = gr.State([])
    last_question_st = gr.State("")
    templates_st     = gr.State([])
    hist_records_st  = gr.State([])   # reversed history list for download lookup
    panel_visible_st  = gr.State(False)
    df_user_st        = gr.State(None)
    user_key_col_st   = gr.State("")
    upload_visible_st = gr.State(False)

    # ── Header ────────────────────────────────────────────────────────────────
    with gr.Row(equal_height=True):
        with gr.Column(scale=7):
            gr.Markdown(
                "## Financial Portfolio Assistant — Architecture 3.0\n"
                "Classify → Pre-route → Agent Orchestrator → Specialist Codegen · Thai Baht (฿)"
            )
        with gr.Column(scale=0, min_width=140):
            module_dd = gr.Dropdown(
                choices=[m.upper() for m in get_modules()],
                value=DEFAULT_MODULE.upper(),
                label="Module",
                interactive=True,
            )
        with gr.Column(scale=0, min_width=240):
            model_dd = gr.Dropdown(
                choices=list(PROVIDERS.keys()),
                value=DEFAULT_PROVIDER,
                label="Model",
                interactive=True,
            )
        with gr.Column(scale=0, min_width=90):
            panel_btn = gr.Button("📋 Report & Template", size="sm")

    # ── Body: side panel + chat ───────────────────────────────────────────────
    with gr.Row():

        # ── Side panel ────────────────────────────────────────────────────────
        with gr.Column(scale=3, min_width=280, visible=False) as side_panel_col:
            with gr.Tabs():

                # ── Templates tab ──────────────────────────────────────────
                with gr.Tab("📋 Templates"):
                    template_radio  = gr.Radio(choices=[], label="", interactive=True)
                    template_detail = gr.Markdown("*Select a template to see details.*")

                    with gr.Row():
                        run_tpl_btn = gr.Button("▶ Run", variant="primary", size="sm")
                        del_tpl_btn = gr.Button("🗑 Delete", variant="stop", size="sm")

                    tpl_status = gr.Markdown("")

                    with gr.Accordion("+ New Template", open=False) as new_tpl_acc:
                        tpl_name_tb   = gr.Textbox(label="Name")
                        tpl_module_dd = gr.Dropdown(
                            choices=["NPL", "NPA"], value="NPL", label="Module"
                        )
                        tpl_desc_tb   = gr.Textbox(label="Description (optional)")
                        tpl_excel_file = gr.File(
                            label="Import columns from Excel (optional)",
                            file_types=[".xlsx", ".xls"],
                            file_count="single",
                        )
                        import_excel_btn = gr.Button("📥 Import Columns", size="sm")
                        import_status = gr.Markdown("", visible=False)
                        tpl_prompt_tb = gr.Textbox(
                            label="Prompt (Thai / English)",
                            lines=5,
                            placeholder="e.g. ขอรายงาน ชื่อลูกหนี้ รหัส ภาระหนี้ พร้อมหลักประกัน งวดล่าสุด",
                        )
                        save_tpl_btn  = gr.Button("💾 Save Template", variant="primary")

                # ── History tab ────────────────────────────────────────────
                with gr.Tab("🕐 History"):
                    history_dd = gr.Dropdown(
                        choices=[],
                        label="Select a report",
                        interactive=True,
                        allow_custom_value=False,
                    )
                    with gr.Row():
                        refresh_hist_btn = gr.Button("🔄 Refresh", size="sm")
                        dl_hist_btn = gr.DownloadButton(
                            "⬇ Download", size="sm", value=None
                        )

        # ── Chat ──────────────────────────────────────────────────────────────
        with gr.Column(scale=7):
            chatbot = gr.Chatbot(
                height=CHAT_HEIGHT,
                label="Chat",
            )

            with gr.Row():
                msg_tb = gr.Textbox(
                    placeholder="Ask a question...",
                    scale=9,
                    show_label=False,
                    container=False,
                    lines=1,
                )
                attach_btn    = gr.Button("📎", scale=0, min_width=44, size="sm")
                submit_btn    = gr.Button("Send", variant="primary", scale=1, min_width=80)
                clear_btn     = gr.Button("Clear", scale=1, min_width=70)

            with gr.Row(visible=False) as upload_row:
                upload_file = gr.File(
                    label="Upload account list (Excel / CSV)",
                    file_types=[".xlsx", ".xls", ".csv"],
                    file_count="single",
                    scale=8,
                )
                clear_upload_btn = gr.Button("✕ Clear", scale=0, min_width=70, size="sm")
            upload_status = gr.Markdown("", visible=False)

            # Appears only after a report is generated
            with gr.Row(visible=False) as report_action_row:
                report_dl_btn   = gr.DownloadButton("⬇ Download Report", value=None)
                save_as_tpl_btn = gr.Button("💾 Save as Template")

    # ── Respond outputs helper (same list for submit + template run) ──────────
    _RESPOND_OUTPUTS = [
        chatbot, msg_tb, our_history_st,
        report_action_row, report_dl_btn, last_question_st,
    ]

    # ── Panel toggle ─────────────────────────────────────────────────────────
    def toggle_panel(is_visible):
        new_val = not is_visible
        return gr.update(visible=new_val), new_val

    panel_btn.click(
        fn=toggle_panel,
        inputs=[panel_visible_st],
        outputs=[side_panel_col, panel_visible_st],
    )

    # ── Chat events ───────────────────────────────────────────────────────────
    _RESPOND_INPUTS = [msg_tb, chatbot, our_history_st, model_dd, module_dd, df_user_st, user_key_col_st]

    submit_btn.click(respond, _RESPOND_INPUTS, _RESPOND_OUTPUTS)
    msg_tb.submit(respond, _RESPOND_INPUTS, _RESPOND_OUTPUTS)

    clear_btn.click(
        fn=lambda: ([], [], ""),
        outputs=[chatbot, our_history_st, last_question_st],
    )

    attach_btn.click(
        fn=lambda v: (gr.update(visible=not v), not v),
        inputs=[upload_visible_st],
        outputs=[upload_row, upload_visible_st],
    )

    def _on_upload(file):
        df, key_col, msg = extract_user_df(file)
        return df, key_col, gr.update(value=msg, visible=bool(msg))

    upload_file.change(
        fn=_on_upload,
        inputs=[upload_file],
        outputs=[df_user_st, user_key_col_st, upload_status],
    )

    clear_upload_btn.click(
        fn=lambda: (None, None, "", gr.update(value="", visible=False), gr.update(visible=False), False),
        outputs=[upload_file, df_user_st, user_key_col_st, upload_status, upload_row, upload_visible_st],
    )

    # ── Template events ───────────────────────────────────────────────────────

    template_radio.change(
        fn=on_template_select,
        inputs=[template_radio, templates_st],
        outputs=[template_detail],
    )

    # Run template: load prompt + module → then submit to chat
    run_tpl_btn.click(
        fn=load_template_prompt,
        inputs=[template_radio, templates_st],
        outputs=[msg_tb, module_dd],
    ).then(
        fn=respond,
        inputs=_RESPOND_INPUTS,
        outputs=_RESPOND_OUTPUTS,
    )

    del_tpl_btn.click(
        fn=do_delete_template,
        inputs=[template_radio, templates_st],
        outputs=[template_radio, templates_st, tpl_status],
    )

    import_excel_btn.click(
        fn=import_excel_columns,
        inputs=[tpl_excel_file, tpl_prompt_tb],
        outputs=[tpl_prompt_tb, import_status],
    )

    save_tpl_btn.click(
        fn=do_save_template,
        inputs=[tpl_name_tb, tpl_module_dd, tpl_desc_tb, tpl_prompt_tb, templates_st],
        outputs=[template_radio, templates_st, tpl_status, new_tpl_acc],
    )

    # "Save as Template" — pre-fill form + open side panel so the user sees the form
    save_as_tpl_btn.click(
        fn=prefill_save_as,
        inputs=[last_question_st, module_dd],
        outputs=[side_panel_col, panel_visible_st, new_tpl_acc, tpl_name_tb, tpl_module_dd, tpl_desc_tb, tpl_prompt_tb],
    )

    # ── History events ────────────────────────────────────────────────────────

    refresh_hist_btn.click(
        fn=refresh_history,
        outputs=[history_dd, hist_records_st],
    )

    history_dd.change(
        fn=on_history_change,
        inputs=[history_dd, hist_records_st],
        outputs=[dl_hist_btn],
    )

    # ── On page load ──────────────────────────────────────────────────────────

    def _initial_load():
        templates = load_templates()
        choices   = _template_choices(templates)
        history   = load_history()
        rev       = list(reversed(history))
        hist_choices = _history_choices(rev)
        return (
            gr.update(choices=choices, value=None), templates,
            gr.update(choices=hist_choices, value=None), rev,
        )

    demo.load(
        fn=_initial_load,
        outputs=[template_radio, templates_st, history_dd, hist_records_st],
    )


if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
