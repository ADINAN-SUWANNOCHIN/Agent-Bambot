"""
rag_retriever.py — Hybrid RAG: keyword + Gemini Embedding 2 + ChromaDB Cloud.

Collection structure (per module, not per table):
  _global_gemini2        — domain knowledge shared across all modules
  {module}_gemini2       — column synonyms, query patterns for a specific module
                           (supports table subfolders: knowledge/npl/npl_main/*.md)

At query time both collections are searched, results merged, then hybrid re-ranked.
Vectors persist in ChromaDB Cloud — only new/changed chunks are re-embedded on startup.
"""
import os
import re
import hashlib
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
KNOWLEDGE_DIR = Path(__file__).parent.parent / "knowledge"
GLOBAL_DIR    = KNOWLEDGE_DIR / "_global"

# ── Active module (set by UI or app startup) ───────────────────────────────────
_active_module: str = "npl"

# ── Chunk caches (invalidated when module changes) ─────────────────────────────
_chunks_global: list[dict] | None = None
_chunks_module: list[dict] | None = None

# ── ChromaDB client + collection cache ────────────────────────────────────────
_chroma_client       = None
_global_collection   = None
_module_collection   = None

# ── Embedding config ───────────────────────────────────────────────────────────
_EMBED_MODEL = "gemini-embedding-2-preview"
_EMBED_BATCH  = 50


def set_module(name: str) -> None:
    """Switch active module. Invalidates module chunk cache and collection reference."""
    global _active_module, _chunks_module, _module_collection
    if name != _active_module:
        _active_module     = name
        _chunks_module     = None
        _module_collection = None


# ── Markdown parsing ───────────────────────────────────────────────────────────

def _parse_md(md_file: Path, module: str, table: str) -> list[dict]:
    """Split a markdown file into ## section chunks with module/table metadata."""
    text = md_file.read_text(encoding="utf-8")
    chunks, current_section, current_lines = [], "intro", []

    for line in text.split("\n"):
        if line.startswith("## "):
            if current_lines:
                body = "\n".join(current_lines).strip()
                if len(body) > 30:
                    chunks.append({
                        "text": body,
                        "section": current_section,
                        "source": md_file.stem,
                        "module": module,
                        "table": table,
                    })
            current_section = line[3:].strip()
            current_lines   = [line]
        else:
            current_lines.append(line)

    if current_lines:
        body = "\n".join(current_lines).strip()
        if len(body) > 30:
            chunks.append({
                "text": body,
                "section": current_section,
                "source": md_file.stem,
                "module": module,
                "table": table,
            })
    return chunks


def _load_global_chunks() -> list[dict]:
    global _chunks_global
    if _chunks_global is not None:
        return _chunks_global
    _chunks_global = []
    if GLOBAL_DIR.exists():
        for md_file in sorted(GLOBAL_DIR.glob("*.md")):
            _chunks_global.extend(_parse_md(md_file, module="_global", table="_global"))
    return _chunks_global


def _load_module_chunks() -> list[dict]:
    """Load all .md files from knowledge/{module}/ recursively.
    Files in subfolders (table-level) get the subfolder name as their table tag."""
    global _chunks_module
    if _chunks_module is not None:
        return _chunks_module
    _chunks_module = []
    module_dir = KNOWLEDGE_DIR / _active_module
    if not module_dir.exists():
        return _chunks_module
    for md_file in sorted(module_dir.glob("**/*.md")):
        # If file is inside a subfolder of the module dir → subfolder = table name
        relative = md_file.relative_to(module_dir)
        table = relative.parts[0] if len(relative.parts) > 1 else _active_module
        _chunks_module.extend(_parse_md(md_file, module=_active_module, table=table))
    return _chunks_module


# ── ChromaDB ───────────────────────────────────────────────────────────────────

def _get_chroma_client():
    global _chroma_client
    if _chroma_client is None:
        import chromadb
        _chroma_client = chromadb.CloudClient(
            api_key=os.environ.get("CHROMA_API_KEY", ""),
            tenant=os.environ.get("CHROMA_TENANT", ""),
            database=os.environ.get("CHROMA_DATABASE", ""),
        )
    return _chroma_client


def _get_global_collection():
    global _global_collection
    if _global_collection is None:
        _global_collection = _get_chroma_client().get_or_create_collection(
            name="global_gemini2",
            metadata={"hnsw:space": "cosine"},
        )
    return _global_collection


def _get_module_collection():
    global _module_collection
    if _module_collection is None:
        _module_collection = _get_chroma_client().get_or_create_collection(
            name=f"{_active_module}_gemini2",
            metadata={"hnsw:space": "cosine"},
        )
    return _module_collection


# ── Gemini Embedding 2 ─────────────────────────────────────────────────────────

def _gemini_embed(texts: list[str]) -> list[list[float]] | None:
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return None
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        all_vecs = []
        for text in texts:
            resp = client.models.embed_content(model=_EMBED_MODEL, contents=text)
            all_vecs.append(resp.embeddings[0].values)
        return all_vecs
    except Exception as exc:
        print(f"[RAG] Gemini embedding failed: {exc}")
        return None


# ── Sync chunks → ChromaDB ─────────────────────────────────────────────────────

def _chunk_id(i: int, chunk: dict) -> str:
    content_hash = hashlib.md5(chunk["text"].encode()).hexdigest()[:8]
    raw = f"{chunk['module']}|{chunk['source']}|{i}|{content_hash}"
    return hashlib.md5(raw.encode()).hexdigest()


def _sync(chunks: list[dict], get_collection_fn) -> bool:
    """Upsert only chunks not yet in the collection. Returns True if collection is usable."""
    if not chunks:
        return False
    try:
        collection = get_collection_fn()
        ids = [_chunk_id(i, c) for i, c in enumerate(chunks)]

        existing    = collection.get(ids=ids, include=[])
        existing_ids = set(existing["ids"])
        new_idx     = [i for i, id_ in enumerate(ids) if id_ not in existing_ids]

        if not new_idx:
            return True

        new_texts = [chunks[i]["text"] for i in new_idx]
        new_ids   = [ids[i] for i in new_idx]
        new_metas = [{
            "module":  chunks[i]["module"],
            "table":   chunks[i]["table"],
            "source":  chunks[i]["source"],
            "section": chunks[i]["section"],
        } for i in new_idx]

        print(f"[RAG] Embedding {len(new_idx)} new chunk(s) → {get_collection_fn.__name__}...")
        embeddings = _gemini_embed(new_texts)
        if embeddings is None:
            return False

        collection.upsert(ids=new_ids, embeddings=embeddings, documents=new_texts, metadatas=new_metas)
        print(f"[RAG] {len(new_idx)} chunk(s) synced.")
        return True

    except Exception as exc:
        print(f"[RAG] Sync failed: {exc}")
        return False


# ── Keyword scoring ────────────────────────────────────────────────────────────

def _tokenize(text: str) -> set[str]:
    parts = re.split(r'[\s,.()\[\]/|:=+\-*\'"`#\n\r→]+', text.lower())
    return {p for p in parts if len(p) > 1}


def _keyword_score(query_tokens: set[str], chunk_text: str) -> float:
    if not query_tokens:
        return 0.0
    chunk_tokens = _tokenize(chunk_text)
    chunk_lower  = chunk_text.lower()
    exact  = query_tokens & chunk_tokens
    substr = {qt for qt in query_tokens - exact if len(qt) > 2 and qt in chunk_lower}
    matched  = len(exact) + len(substr) * 0.5
    coverage = matched / len(query_tokens)
    density  = len(exact) / max(len(chunk_tokens), 1)
    return coverage * 0.7 + density * 0.3


# ── Vector search helper ───────────────────────────────────────────────────────

def _vector_search(collection, q_emb: list, n: int) -> tuple[list, list, list]:
    """Query ChromaDB. Returns (docs, metas, similarities). Empty lists on error."""
    try:
        count = collection.count()
        if count == 0:
            return [], [], []
        n = min(n, count)
        res = collection.query(
            query_embeddings=q_emb,
            n_results=n,
            include=["documents", "metadatas", "distances"],
        )
        docs      = res["documents"][0]
        metas     = res["metadatas"][0]
        sims      = [max(0.0, 1.0 - d) for d in res["distances"][0]]
        return docs, metas, sims
    except Exception as exc:
        print(f"[RAG] Vector search failed: {exc}")
        return [], [], []


# ── Hybrid retrieval ───────────────────────────────────────────────────────────

_KEYWORD_WEIGHT = 0.40
_VECTOR_WEIGHT  = 0.60


def retrieve(query: str, n_results: int = 6) -> str:
    """Hybrid retrieval across _global + active module collections.

    Steps:
      1. Sync any new chunks to ChromaDB (once per session)
      2. Embed query via Gemini Embedding 2
      3. Search both collections (n_results candidates each)
      4. Merge candidates, hybrid re-rank (40% keyword + 60% vector)
      5. Return top n_results chunks
    Fallback: keyword-only on all chunks if ChromaDB / Gemini unavailable."""

    global_chunks = _load_global_chunks()
    module_chunks = _load_module_chunks()
    all_chunks    = global_chunks + module_chunks

    if not all_chunks:
        return ""

    # Sync both collections (only embeds new chunks)
    global_ok = _sync(global_chunks, _get_global_collection)
    module_ok = _sync(module_chunks, _get_module_collection)

    query_tokens = _tokenize(query)

    if global_ok or module_ok:
        q_emb = _gemini_embed([query])
        if q_emb is not None:
            # Search both collections; fetch extra candidates for re-ranking
            n_candidates = n_results * 2

            g_docs, g_metas, g_sims = _vector_search(_get_global_collection(), q_emb, n_candidates) if global_ok else ([], [], [])
            m_docs, m_metas, m_sims = _vector_search(_get_module_collection(),  q_emb, n_candidates) if module_ok  else ([], [], [])

            # Merge candidates from both collections
            all_docs  = g_docs  + m_docs
            all_metas = g_metas + m_metas
            all_sims  = g_sims  + m_sims

            if all_docs:
                # Hybrid re-rank
                kw_scores = [_keyword_score(query_tokens, doc) for doc in all_docs]
                max_kw    = max(kw_scores) if max(kw_scores) > 0 else 1.0
                combined  = [
                    (kw / max_kw) * _KEYWORD_WEIGHT + vs * _VECTOR_WEIGHT
                    for kw, vs in zip(kw_scores, all_sims)
                ]

                ranked    = sorted(zip(all_docs, all_metas, combined), key=lambda x: x[2], reverse=True)
                formatted = [f"[{m['source']}]\n{doc}" for doc, m, _ in ranked[:n_results]]
                return "\n\n---\n\n".join(formatted)

    # ── Keyword-only fallback ──────────────────────────────────────────────────
    scored = sorted(all_chunks, key=lambda c: _keyword_score(query_tokens, c["text"]), reverse=True)
    return "\n\n---\n\n".join(f"[{c['source']}]\n{c['text']}" for c in scored[:n_results])
