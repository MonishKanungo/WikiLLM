"""
WikiLLM Engine
Implements the three core operations:
  - ingest_document(text, filename, llm_fn) -> list[str]  (pages updated)
  - query_wiki(question, llm_fn) -> (answer, cited_pages)
  - lint_wiki(llm_fn) -> str
Wiki lives at WIKI_DIR (created on startup).
"""

import os
import re
import json
from datetime import datetime
from pathlib import Path

# Detect Vercel environment for storage paths
if os.environ.get("VERCEL"):
    WIKI_DIR = Path("/tmp/wiki")
else:
    WIKI_DIR = Path(__file__).parent.parent / "wiki"

PAGES_DIR = WIKI_DIR / "pages"
INDEX_FILE = WIKI_DIR / "index.md"
LOG_FILE = WIKI_DIR / "log.md"

# ── helpers ──────────────────────────────────────────────────────────────────

def _ensure_dirs():
    PAGES_DIR.mkdir(parents=True, exist_ok=True)
    if not INDEX_FILE.exists():
        INDEX_FILE.write_text("# Wiki Index\n\n| Page | Summary |\n|------|---------|\n", encoding="utf-8")
    if not LOG_FILE.exists():
        LOG_FILE.write_text("# Wiki Log\n\n", encoding="utf-8")


def _read_index() -> str:
    _ensure_dirs()
    return INDEX_FILE.read_text(encoding="utf-8")


def _read_page(name: str) -> str:
    path = PAGES_DIR / f"{name}.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def _write_page(name: str, content: str):
    path = PAGES_DIR / f"{name}.md"
    path.write_text(content, encoding="utf-8")


def _list_pages() -> list[str]:
    _ensure_dirs()
    return [p.stem for p in sorted(PAGES_DIR.glob("*.md"))]


def _append_log(entry: str):
    _ensure_dirs()
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(entry + "\n\n")


def _update_index(name: str, summary: str):
    """Upsert a row in index.md for the given page name."""
    index_content = _read_index()
    row = f"| [{name}](pages/{name}.md) | {summary} |"
    # Remove existing row for this page if present
    lines = index_content.splitlines()
    new_lines = [l for l in lines if not re.match(rf"^\|\s*\[?{re.escape(name)}\]?", l)]
    new_lines.append(row)
    INDEX_FILE.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


# ── ingest ───────────────────────────────────────────────────────────────────

INGEST_SYSTEM = """You are a meticulous wiki editor maintaining a personal knowledge base.
Given a source document, extract the key information and return a JSON object.

Return ONLY valid JSON (no extra text, no markdown fences, no comments) with this EXACT structure:
{
  "summary_page": {
    "name": "snake_case_slug_no_spaces",
    "title": "Human Readable Title",
    "content": "full markdown content for this page"
  },
  "entity_pages": [
    {
      "name": "entity_slug",
      "title": "Entity Name",
      "content": "markdown content"
    }
  ],
  "one_line_summary": "one sentence summary of the source document"
}

Rules:
- summary_page captures the overall source document as a markdown page.
- entity_pages cover important people, places, concepts, or topics from the source. Can be empty array [].
- All content should use clean markdown with headings and bullet points.
- Cross-reference related pages using [[page-name]] syntax.
- The "name" fields must be snake_case with no spaces or special characters.
- Be thorough but concise.
- Return ONLY the JSON object. No preamble, no explanation.
"""


def ingest_document(text: str, filename: str, llm_fn) -> list[str]:
    """Process a document and update the wiki. Returns list of page names updated."""
    _ensure_dirs()

    user_prompt = f"Source document filename: {filename}\n\n---\n\n{text[:12000]}"  # cap at ~12k chars

    raw = llm_fn(INGEST_SYSTEM, user_prompt)
    original_raw = raw  # keep for error reporting

    # Strategy 1: strip ```json ... ``` fences
    json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw)
    if json_match:
        raw = json_match.group(1).strip()

    # Strategy 2: find the outermost { ... } if still not clean JSON
    if not raw.strip().startswith("{"):
        brace_match = re.search(r"\{[\s\S]*\}", raw)
        if brace_match:
            raw = brace_match.group(0)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"LLM returned invalid JSON.\nParse error: {e}\n"
            f"--- Raw LLM output (first 500 chars) ---\n{original_raw[:500]}"
        )

    updated = []

    # Write summary page
    sp = data["summary_page"]
    existing = _read_page(sp["name"])
    if existing:
        # Merge: ask LLM to update existing page (keep simple for MVP — just overwrite)
        pass
    _write_page(sp["name"], f"# {sp['title']}\n\n{sp['content']}")
    _update_index(sp["name"], data.get("one_line_summary", sp["title"]))
    updated.append(sp["name"])

    # Write entity pages
    for ep in data.get("entity_pages", []):
        existing = _read_page(ep["name"])
        if existing:
            merge_prompt = (
                f"Existing wiki page for '{ep['name']}':\n\n{existing}\n\n"
                f"New information to integrate:\n\n{ep['content']}\n\n"
                "Return the updated, merged markdown page. Keep all existing info; add new info; note contradictions. "
                "Return ONLY the markdown, no commentary."
            )
            merged = llm_fn("You are a wiki editor. Merge the new information into the existing page carefully.", merge_prompt)
            _write_page(ep["name"], merged)
        else:
            _write_page(ep["name"], f"# {ep['title']}\n\n{ep['content']}")
            _update_index(ep["name"], ep["title"])
        updated.append(ep["name"])

    # Log the ingest
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    _append_log(f"## [{ts}] ingest | {filename}\nPages updated: {', '.join(updated)}")

    return updated


# ── query ────────────────────────────────────────────────────────────────────

QUERY_SYSTEM = """You are a knowledgeable assistant with access to a personal wiki knowledge base.
You will be given:
1. The wiki index (a table of all pages with summaries)
2. The content of the most relevant pages

Your task: Answer the user's question accurately, citing the wiki pages you used.
Format your answer in clean markdown.
At the end, list citations as: **Sources:** page-name1, page-name2
"""

def query_wiki(question: str, llm_fn) -> tuple[str, list[str]]:
    """Answer a question using the wiki. Returns (answer, cited_pages)."""
    _ensure_dirs()

    index = _read_index()
    page_names = _list_pages()

    if not page_names:
        return "The wiki is empty. Please ingest some documents first.", []

    # Step 1: ask LLM which pages are most relevant
    select_system = "You are a search assistant. Given a wiki index table and a question, return ONLY a JSON array of the page names (slugs) most relevant to answer the question. Return at most 5 pages. Example: [\"page_one\", \"page_two\"]"
    select_user = f"Wiki index:\n\n{index}\n\nQuestion: {question}"
    raw_pages = llm_fn(select_system, select_user)

    # Parse page list
    arr_match = re.search(r"\[.*?\]", raw_pages, re.DOTALL)
    relevant_names = []
    if arr_match:
        try:
            relevant_names = json.loads(arr_match.group(0))
        except json.JSONDecodeError:
            relevant_names = page_names[:3]
    else:
        relevant_names = page_names[:3]

    # Step 2: load those pages
    pages_content = ""
    cited = []
    for name in relevant_names:
        content = _read_page(name)
        if content:
            pages_content += f"\n\n---\n### Page: {name}\n\n{content}"
            cited.append(name)

    # Step 3: synthesize answer
    user_prompt = f"Wiki index:\n\n{index}\n\nRelevant wiki pages:{pages_content}\n\nQuestion: {question}"
    answer = llm_fn(QUERY_SYSTEM, user_prompt)

    # Log query
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    _append_log(f"## [{ts}] query | {question[:80]}\nPages consulted: {', '.join(cited)}")

    return answer, cited


# ── lint ─────────────────────────────────────────────────────────────────────

LINT_SYSTEM = """You are a wiki health inspector.
You will be given the wiki index and all page contents.
Identify and report:
1. Orphan pages (no inbound [[links]] from other pages)
2. Contradictions between pages
3. Stale or vague claims that need updating
4. Important concepts mentioned but lacking their own page
5. Missing cross-references

Format your report as markdown with sections for each issue type.
Be specific — name the pages involved.
"""

def lint_wiki(llm_fn) -> str:
    """Health-check the wiki. Returns a markdown report."""
    _ensure_dirs()
    page_names = _list_pages()
    if not page_names:
        return "Wiki is empty — nothing to lint."

    all_content = f"## Wiki Index\n\n{_read_index()}\n\n"
    for name in page_names:
        content = _read_page(name)
        all_content += f"---\n### Page: {name}\n\n{content}\n\n"

    report = llm_fn(LINT_SYSTEM, all_content[:15000])

    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    _append_log(f"## [{ts}] lint\n{report[:300]}...")

    return report


# ── save answer ──────────────────────────────────────────────────────────────

def save_answer_as_page(page_name: str, page_title: str, content: str) -> str:
    """
    Save a query answer back into the wiki as a new page.
    This implements the WikiLLM principle:
      'Good answers can be filed back into the wiki as new pages.'
    Returns the page name written.
    """
    _ensure_dirs()

    # Sanitize the page name — snake_case, no spaces
    safe_name = re.sub(r"[^\w]", "_", page_name.strip().lower()).strip("_")
    if not safe_name:
        safe_name = "saved_answer"

    # Build full page content with a header noting it was a query result
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    full_content = f"# {page_title}\n\n> 💡 *Saved from query on {ts}*\n\n{content}"

    _write_page(safe_name, full_content)
    _update_index(safe_name, f"[Query answer] {page_title}")
    _append_log(f"## [{ts}] query→wiki | {page_title}\nSaved answer as page: {safe_name}")

    return safe_name


# ── reset ────────────────────────────────────────────────────────────────────

def reset_wiki():
    """Delete all wiki content."""
    import shutil
    if WIKI_DIR.exists():
        shutil.rmtree(WIKI_DIR)
    _ensure_dirs()

