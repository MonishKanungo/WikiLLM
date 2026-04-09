# 📚 WikiLLM

> **A document intelligence app that builds a persistent, compounding knowledge base — not just a search index.**

---

## 🚀 Quick Start

```bash
# 1. Install dependencies
pip install -r backend/requirements.txt

# 2. Start the server (also serves the frontend)
cd backend
uvicorn main:app --reload --port 8000

# 3. Open in browser
http://localhost:8000
```

---

## 📁 Project Structure

```
wikiLLM/
├── backend/
│   ├── main.py            # FastAPI app — all API endpoints
│   ├── wiki_engine.py     # Core WikiLLM logic (ingest, query, lint)
│   ├── litellm_client.py  # LiteLLM wrapper (any provider, any API key)
│   ├── models.py          # Pydantic request/response schemas
│   └── requirements.txt
├── frontend/
│   └── index.html         # Premium dark-mode SPA
├── wiki/                  # Auto-generated, persists on disk
│   ├── index.md           # Master index of all wiki pages
│   ├── log.md             # Append-only activity log
│   └── pages/             # One .md file per entity/concept/source
└── wikillm.md             # Original pattern description
```

---

## 🔑 How API Keys Are Stored

**Short answer: they are NOT stored anywhere on the server.**

Here is the full data flow:

```
Browser → [API key in request body] → FastAPI → LiteLLM → LLM Provider
                                           ↑
                                     Key used once,
                                     never written to disk
```

| Where | Stored? | Details |
|-------|---------|---------|
| Server disk | ❌ No | `litellm_client.py` only uses the key in-memory for the duration of a single request |
| Server memory (persistent) | ❌ No | Each request creates a fresh `llm_fn` from scratch |
| Browser `localStorage` | ❌ No | Key lives only in the `<input>` field in RAM |
| Network logs | ⚠️ HTTPS only | Always use HTTPS in production to prevent interception |
| Wiki files | ❌ No | Only your document content and LLM-generated summaries are saved |

> **Design choice:** The API key travels with every request from the browser. This is intentional for simplicity — no sessions, no database, no server config needed. In production, add HTTPS and optionally a server-side session store.

---

## 🧠 WikiLLM vs RAG — A Deep Comparison

### Types of RAG (what most systems do)

| Type | How it works | Limitation |
|------|-------------|------------|
| **Naive RAG** | Chunk docs → embed → retrieve top-K at query time → generate | Re-derives knowledge every query; no memory |
| **Advanced RAG** | Adds re-ranking, query rewriting, hybrid search (BM25 + vector) | Still stateless; no accumulated understanding |
| **Modular RAG** | Pluggable retrieval pipelines, iterative retrieval, fusion | Complex infra; each query still starts from raw chunks |
| **Agentic RAG** | LLM decides what to retrieve, multi-hop reasoning | Expensive; still reads raw sources repeatedly |
| **Graph RAG** *(Microsoft)* | Builds an entity graph at index time; queries traverse the graph | Closer to WikiLLM but graph is implicit, not human-readable |

---

### How WikiLLM is Different

```
┌─────────────────────────────────────────────────────────────────┐
│                        Traditional RAG                          │
│                                                                 │
│  Raw Docs → [Chunk] → [Embed] → Vector DB                      │
│                                      ↓                          │
│                              Query → Retrieve chunks            │
│                                      ↓                          │
│                              Generate answer (from raw chunks)  │
│                                                                 │
│  ❌ Knowledge is never accumulated                               │
│  ❌ Same synthesis work repeated on every query                  │
│  ❌ No cross-document connections pre-built                      │
│  ❌ Contradictions never flagged                                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                          WikiLLM                                │
│                                                                 │
│  Raw Docs → [Ingest] → LLM builds wiki pages (once)            │
│                              ↓                                  │
│                         Persistent Wiki (markdown files)        │
│                         - Cross-references already built        │
│                         - Contradictions already flagged        │
│                         - Entities already extracted            │
│                              ↓                                  │
│  Query → Read index → Load relevant pages → Answer              │
│                                                                 │
│  ✅ Knowledge compounds with every doc added                     │
│  ✅ Synthesis done ONCE at ingest, not per-query                 │
│  ✅ Human-readable — you can browse and edit the wiki            │
│  ✅ Cross-references, summaries, entities pre-built              │
│  ✅ Works without embeddings or vector DB                        │
└─────────────────────────────────────────────────────────────────┘
```

### Head-to-Head

| Feature | Naive RAG | Graph RAG | **WikiLLM** |
|---------|-----------|-----------|-------------|
| Knowledge accumulates over time | ❌ | ⚠️ Partial | ✅ |
| Human-readable knowledge store | ❌ | ❌ | ✅ |
| Works without vector DB | ❌ | ❌ | ✅ |
| Cross-references pre-built | ❌ | ✅ | ✅ |
| Contradiction detection | ❌ | ⚠️ | ✅ (lint) |
| Query cost (LLM calls) | High (per query) | Medium | Low (wiki pre-built) |
| Ingest cost (LLM calls) | Low (just embed) | Medium | Medium |
| Supports any LLM provider | Depends | Depends | ✅ (LiteLLM) |
| Knowledge browsable by human | ❌ | ❌ | ✅ |

---

## ⚙️ Supported LLM Providers

WikiLLM uses [LiteLLM](https://docs.litellm.ai/) under the hood, so it supports **100+ models** with a unified interface:

| Provider | Example Model String |
|----------|---------------------|
| OpenAI | `openai/gpt-4o-mini` |
| Anthropic | `anthropic/claude-3-5-haiku-20241022` |
| Google Gemini | `gemini/gemini-1.5-flash` |
| Groq | `groq/llama-3.1-8b-instant` |
| Mistral | `mistral/mistral-small-latest` |
| Cohere | `cohere/command-r` |
| Local (Ollama) | `openai/llama3` + base URL `http://localhost:11434` |

---

## 🔧 API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/ingest` | Upload a document (multipart form: `file` + `llm_config` JSON) |
| `POST` | `/api/query` | Ask a question (`{ question, llm: { model, api_key } }`) |
| `POST` | `/api/lint` | Run wiki health check |
| `GET` | `/api/wiki` | List all wiki page names |
| `GET` | `/api/wiki/{page}` | Read a specific wiki page |
| `GET` | `/api/wiki/index` | Read raw `index.md` |
| `GET` | `/api/wiki/log` | Read raw `log.md` |
| `DELETE` | `/api/wiki` | Reset entire wiki |

---

## 📄 Supported File Types

| Extension | Notes |
|-----------|-------|
| `.txt` | Plain text |
| `.md` | Markdown |
| `.pdf` | Text extraction via PyPDF2 |
| `.docx` | Text extraction via python-docx |

---

## 🔍 How Ingest Works (3 steps)

1. **Extract** — File is uploaded, text is extracted based on type
2. **LLM Processing** — The LLM reads the document and returns structured JSON:
   - A `summary_page` for the overall document
   - `entity_pages` for key people, places, concepts
3. **Wiki Update** — Pages are written/merged into `wiki/pages/`, index is updated, log entry appended

---

## 💬 How Query Works (2 steps)

1. **Retrieval** — LLM reads `index.md` and selects the most relevant page names (no vector DB needed)
2. **Synthesis** — LLM reads those pages and generates a cited answer

---

## 🏥 Wiki Lint

Click **"Lint"** in the app to run a health check that identifies:
- Orphan pages (no inbound links)
- Contradictions between pages
- Stale claims superseded by newer docs
- Concepts mentioned but lacking their own page
- Missing cross-references

---

## 🛡️ Security Notes

- API keys are **never stored on disk or in memory beyond a single request**
- The `wiki/` directory contains only LLM-generated summaries of your documents
- For production use: add HTTPS, restrict CORS origins, and consider server-side auth

---

*Built on the [WikiLLM pattern](./wikillm.md) — a persistent, compounding alternative to RAG.*
