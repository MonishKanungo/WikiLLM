"""
WikiLLM FastAPI Backend
Serves the frontend as static files from ../frontend/
and exposes REST API for ingest, query, wiki browsing, and lint.
"""

import io
import json
import os
import traceback
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from models import (
    QueryRequest, QueryResponse,
    IngestResponse, WikiListResponse, WikiPage,
    LintRequest, LLMConfig,
    SaveAnswerRequest, SaveAnswerResponse,
)
from litellm_client import make_llm_fn
import wiki_engine as wiki

app = FastAPI(title="WikiLLM", version="1.0.0")

# Allow local dev (opening index.html directly from disk)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

IS_VERCEL = bool(os.environ.get("VERCEL"))


# ── text extraction helpers ─────────────────────────────────────────────────

def extract_text(filename: str, data: bytes) -> str:
    ext = Path(filename).suffix.lower()
    if ext in (".txt", ".md"):
        return data.decode("utf-8", errors="replace")
    elif ext == ".pdf":
        try:
            import PyPDF2, io as _io
            reader = PyPDF2.PdfReader(_io.BytesIO(data))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"PDF extraction failed: {e}")
    elif ext in (".docx",):
        try:
            import docx, io as _io
            doc = docx.Document(_io.BytesIO(data))
            return "\n".join(para.text for para in doc.paragraphs)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"DOCX extraction failed: {e}")
    else:
        # Try to decode as UTF-8 as fallback
        try:
            return data.decode("utf-8", errors="replace")
        except Exception:
            raise HTTPException(status_code=415, detail=f"Unsupported file type: {ext}")


# ── API routes ──────────────────────────────────────────────────────────────

@app.post("/api/ingest", response_model=IngestResponse)
async def ingest(
    file: UploadFile = File(...),
    llm_config: str = Form(...),   # JSON-encoded LLMConfig
):
    """Upload a document and integrate it into the wiki."""
    try:
        config = LLMConfig(**json.loads(llm_config))
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid llm_config: {e}")

    data = await file.read()
    text = extract_text(file.filename, data)

    if not text.strip():
        raise HTTPException(status_code=422, detail="Document appears to be empty or unreadable.")

    llm_fn = make_llm_fn(config)

    try:
        updated = wiki.ingest_document(text, file.filename, llm_fn)
    except json.JSONDecodeError as e:
        tb = traceback.format_exc()
        print("[INGEST ERROR - JSONDecodeError]\n", tb)
        raise HTTPException(status_code=500, detail=f"LLM returned invalid JSON during ingest: {e}")
    except Exception as e:
        tb = traceback.format_exc()
        print("[INGEST ERROR]\n", tb)
        raise HTTPException(status_code=500, detail=str(e))

    return IngestResponse(
        message=f"Successfully ingested '{file.filename}'",
        pages_updated=updated,
    )


@app.post("/api/query", response_model=QueryResponse)
async def query(req: QueryRequest):
    """Ask a question; the LLM answers from the wiki."""
    llm_fn = make_llm_fn(req.llm)
    try:
        answer, cited = wiki.query_wiki(req.question, llm_fn)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return QueryResponse(answer=answer, cited_pages=cited)


@app.post("/api/lint")
async def lint(req: LintRequest):
    """Health-check the wiki and return a markdown report."""
    llm_fn = make_llm_fn(req.llm)
    try:
        report = wiki.lint_wiki(llm_fn)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"report": report}


@app.get("/api/wiki", response_model=WikiListResponse)
def list_wiki():
    """List all wiki page names."""
    return WikiListResponse(pages=wiki._list_pages())


# IMPORTANT: specific routes must come BEFORE wildcard {page_name}
@app.get("/api/wiki/index")
def get_index():
    """Return the raw index.md content."""
    wiki._ensure_dirs()
    return {"content": wiki.INDEX_FILE.read_text(encoding="utf-8")}


@app.get("/api/wiki/log")
def get_log():
    """Return the raw log.md content."""
    wiki._ensure_dirs()
    return {"content": wiki.LOG_FILE.read_text(encoding="utf-8")}


@app.delete("/api/wiki")
def reset():
    """Wipe the entire wiki."""
    wiki.reset_wiki()
    return {"message": "Wiki has been reset."}


@app.post("/api/wiki/save-answer", response_model=SaveAnswerResponse)
def save_answer(req: SaveAnswerRequest):
    """
    Save a query answer back into the wiki as a permanent page.
    Implements the WikiLLM principle: good answers compound the knowledge base.
    """
    try:
        saved_name = wiki.save_answer_as_page(req.page_name, req.page_title, req.content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return SaveAnswerResponse(
        message=f"Answer saved as wiki page '{saved_name}'",
        page_name=saved_name,
    )


@app.get("/api/wiki/{page_name}", response_model=WikiPage)
def get_page(page_name: str):
    """Read a specific wiki page."""
    content = wiki._read_page(page_name)
    if not content:
        raise HTTPException(status_code=404, detail=f"Page '{page_name}' not found.")
    return WikiPage(name=page_name, content=content)


# ── Serve frontend ──────────────────────────────────────────────────────────
# On Vercel, static files are served directly by vercel.json routing.
# Locally, FastAPI mounts the frontend directory.
if not IS_VERCEL and FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
elif not IS_VERCEL:
    @app.get("/")
    def root():
        return {"message": "Frontend not found. Place files in ../frontend/"}
