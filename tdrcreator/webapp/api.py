"""
TdrCreator Web API – FastAPI backend.

Environment variables (all optional, sane defaults for Docker):
  TDR_DATA_DIR    Base directory for all data (default: /data)
  TDR_CONFIG_PATH Override config.yaml path
  TDR_HOST        Bind host (default: 0.0.0.0)
  TDR_PORT        Bind port (default: 8000)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Optional

import yaml
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

# ---------------------------------------------------------------------------
# Paths & environment
# ---------------------------------------------------------------------------

DATA_DIR = Path(os.getenv("TDR_DATA_DIR", "/data"))
CONFIG_PATH = Path(os.getenv("TDR_CONFIG_PATH", str(DATA_DIR / "config.yaml")))
DOCS_DIR = DATA_DIR / "docs"
INDEX_DIR = DATA_DIR / ".tdr_index"
OUT_DIR = DATA_DIR / "out"
STATIC_DIR = Path(__file__).parent / "static"

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".md", ".txt", ".rst", ".html", ".htm"}

# Valid subfolders for source typing (must match parser.DOC_TYPE_FOLDERS)
DOC_TYPE_SUBFOLDERS = {"intern", "schulung", "entwurf", "extern", "literatur"}

# ---------------------------------------------------------------------------
# Task registry (in-memory, single-user tool)
# ---------------------------------------------------------------------------

@dataclass
class Task:
    task_id: str
    name: str
    status: str = "running"               # running | done | error
    messages: asyncio.Queue = field(default_factory=asyncio.Queue)
    result: Optional[dict] = None
    error: Optional[str] = None


_tasks: dict[str, Task] = {}


# ---------------------------------------------------------------------------
# Logging bridge: captures library logs → task message queue
# ---------------------------------------------------------------------------

class _QueueHandler(logging.Handler):
    """Forwards log records into an asyncio.Queue from any thread."""

    def __init__(self, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop) -> None:
        super().__init__()
        self.queue = queue
        self.loop = loop

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = {
                "type": "log",
                "level": record.levelname,
                "msg": self.format(record),
            }
            asyncio.run_coroutine_threadsafe(self.queue.put(msg), self.loop)
        except Exception:
            pass


def _attach_queue_handler(task: Task, loop: asyncio.AbstractEventLoop) -> _QueueHandler:
    handler = _QueueHandler(task.messages, loop)
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler.setLevel(logging.DEBUG)
    logging.getLogger("tdrcreator").addHandler(handler)
    return handler


def _detach_handler(handler: _QueueHandler) -> None:
    logging.getLogger("tdrcreator").removeHandler(handler)


# ---------------------------------------------------------------------------
# Default config.yaml for Docker
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = {
    "project_title": "Mein TDR-Projekt",
    "topic": "Bitte hier das Thema eintragen",
    "audience": "technische Stakeholder",
    "language": "de",
    "tone": "formal",
    "target_words": 6000,
    "detail_level": "med",
    "citation_style": "apa",
    "scientific_mode": True,
    "llm_base_url": "http://ollama:11434",
    "llm_model": "llama3",
    "llm_temperature": 0.2,
    "llm_timeout": 120,
    "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
    "retrieval": {
        "chunk_size": 512,
        "overlap": 64,
        "top_k": 8,
        "mmr": True,
        "mmr_lambda": 0.6,
    },
    "literature": {
        "enabled": True,
        "max_papers": 20,
        "year_range": [2015, 2026],
        "allowed_keywords": [],
        "query_guard": False,
        "sources": ["crossref", "openalex", "arxiv"],
    },
    "sections": {
        "abstract": True,
        "context_scope": True,
        "methodology": True,
        "results": True,
        "decisions": True,
        "operations": True,
        "risks": True,
        "glossary": True,
        "references": True,
        "internal_sources": True,
        "appendix": True,
    },
    "output": {
        "md": True,
        "docx": False,
        "pdf": False,
        "output_dir": str(OUT_DIR),
    },
    "privacy": {
        "allow_network_for_literature": True,
        "encrypt_index": False,
    },
    "docs_dir": str(DOCS_DIR),
    "index_dir": str(INDEX_DIR),
}


def _ensure_dirs() -> None:
    for d in (DATA_DIR, DOCS_DIR, OUT_DIR):
        d.mkdir(parents=True, exist_ok=True)
    # Create doc_type subfolders so they show up in the UI immediately
    for subfolder in DOC_TYPE_SUBFOLDERS:
        (DOCS_DIR / subfolder).mkdir(exist_ok=True)


def _ensure_config() -> None:
    if not CONFIG_PATH.exists():
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(
            yaml.dump(DEFAULT_CONFIG, allow_unicode=True, default_flow_style=False),
            encoding="utf-8",
        )


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    _ensure_dirs()
    _ensure_config()
    yield


app = FastAPI(
    title="TdrCreator",
    description="Local-only Transfer Documentation Report generator",
    version="0.1.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Helper: load config
# ---------------------------------------------------------------------------

def _load_config():
    from tdrcreator.config import load_config
    return load_config(CONFIG_PATH)


def _index_stats() -> dict:
    from tdrcreator.retrieval.index import ChunkIndex
    if ChunkIndex.exists(INDEX_DIR):
        try:
            idx = ChunkIndex.load(INDEX_DIR)
            chunks = idx.all_chunks()
            by_file: dict[str, int] = {}
            for c in chunks:
                by_file[Path(c.source_path).name] = by_file.get(Path(c.source_path).name, 0) + 1
            return {
                "exists": True,
                "chunk_count": len(chunks),
                "doc_count": len(by_file),
                "docs": by_file,
            }
        except Exception as e:
            return {"exists": True, "chunk_count": 0, "doc_count": 0, "error": str(e)}
    return {"exists": False, "chunk_count": 0, "doc_count": 0}


def _ollama_status(base_url: str, model: str) -> dict:
    import requests
    try:
        r = requests.get(base_url.rstrip("/") + "/api/tags", timeout=5)
        r.raise_for_status()
        models = [m["name"] for m in r.json().get("models", [])]
        model_available = any(m.startswith(model) for m in models)
        return {"connected": True, "model": model, "model_available": model_available, "models": models}
    except Exception as e:
        return {"connected": False, "model": model, "model_available": False, "models": [], "error": str(e)}


# ---------------------------------------------------------------------------
# Routes: static files & SPA
# ---------------------------------------------------------------------------

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
async def serve_index():
    return FileResponse(str(STATIC_DIR / "index.html"))


# ---------------------------------------------------------------------------
# Routes: status & health
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health():
    return {"ok": True}


@app.get("/api/status")
async def status():
    try:
        cfg = _load_config()
        llm = _ollama_status(cfg.llm_base_url, cfg.llm_model)
    except Exception as e:
        llm = {"connected": False, "error": str(e)}
        cfg = None

    idx = _index_stats()

    docs = list(DOCS_DIR.iterdir()) if DOCS_DIR.exists() else []
    doc_files = [f for f in docs if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS]

    reports = list(OUT_DIR.iterdir()) if OUT_DIR.exists() else []
    report_files = [f for f in reports if f.is_file()]

    return {
        "llm": llm,
        "index": idx,
        "docs_count": len(doc_files),
        "reports_count": len(report_files),
        "config_path": str(CONFIG_PATH),
        "data_dir": str(DATA_DIR),
    }


# ---------------------------------------------------------------------------
# Routes: configuration
# ---------------------------------------------------------------------------

@app.get("/api/config")
async def get_config():
    if not CONFIG_PATH.exists():
        _ensure_config()
    return JSONResponse(content={"yaml": CONFIG_PATH.read_text(encoding="utf-8")})


@app.get("/api/embedding-models")
async def list_embedding_models():
    """Return curated list of embedding model presets for the UI."""
    presets = [
        {
            "id": "sentence-transformers/all-MiniLM-L6-v2",
            "label": "MiniLM-L6-v2 (EN)",
            "size_mb": 80,
            "dim": 384,
            "max_tokens": 256,
            "lang": "en",
            "category": "klein",
            "description": "Sehr schnell, kompakt. Gut fuer englische Texte, schwaecher bei Deutsch.",
        },
        {
            "id": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
            "label": "Multilingual MiniLM-L12",
            "size_mb": 470,
            "dim": 384,
            "max_tokens": 128,
            "lang": "multi",
            "category": "klein",
            "description": "Kompaktes multilinguales Modell. Ordentliche deutsche Qualitaet bei geringem Ressourcenverbrauch.",
        },
        {
            "id": "intfloat/multilingual-e5-small",
            "label": "Multilingual E5 Small",
            "size_mb": 470,
            "dim": 384,
            "max_tokens": 512,
            "lang": "multi",
            "category": "klein",
            "description": "Kleines E5-Modell, 100 Sprachen. Laengere Kontextfenster als MiniLM.",
        },
        {
            "id": "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
            "label": "Multilingual MPNet Base",
            "size_mb": 1100,
            "dim": 768,
            "max_tokens": 128,
            "lang": "multi",
            "category": "mittel",
            "description": "Sehr gute multilinguales Qualitaet. Solider Allrounder fuer Deutsch.",
        },
        {
            "id": "intfloat/multilingual-e5-base",
            "label": "Multilingual E5 Base",
            "size_mb": 1100,
            "dim": 768,
            "max_tokens": 512,
            "lang": "multi",
            "category": "mittel",
            "description": "Starkes multilinguales Retrieval-Modell. Sehr gute Deutsch-Performance.",
        },
        {
            "id": "T-Systems-onsite/cross-en-de-roberta-sentence-transformer",
            "label": "Cross EN-DE RoBERTa",
            "size_mb": 1100,
            "dim": 768,
            "max_tokens": 512,
            "lang": "de/en",
            "category": "mittel",
            "description": "Speziell fuer Deutsch-Englisch trainiert. Top bei gemischtsprachigen Dokumenten.",
        },
        {
            "id": "jinaai/jina-embeddings-v2-base-de",
            "label": "Jina v2 Base DE",
            "size_mb": 640,
            "dim": 768,
            "max_tokens": 8192,
            "lang": "de/en",
            "category": "mittel",
            "description": "Deutsch-optimiert mit 8192 Token Kontext. Ideal fuer lange Dokumente.",
        },
        {
            "id": "intfloat/multilingual-e5-large",
            "label": "Multilingual E5 Large",
            "size_mb": 2240,
            "dim": 1024,
            "max_tokens": 512,
            "lang": "multi",
            "category": "gross",
            "description": "Beste multilinguales Qualitaet. Hoher VRAM-Bedarf (~2.2 GB).",
        },
        {
            "id": "deutsche-telekom/gbert-large-paraphrase-cosine",
            "label": "GBERT Large Paraphrase",
            "size_mb": 1340,
            "dim": 1024,
            "max_tokens": 512,
            "lang": "de",
            "category": "gross",
            "description": "Rein deutsches Modell. Hoechste Qualitaet fuer deutsche Texte (STS 0.855).",
        },
    ]
    return {"models": presets}


@app.post("/api/config")
async def save_config(request: Request):
    body = await request.json()
    yaml_text: str = body.get("yaml", "")
    # Validate YAML syntax
    try:
        parsed = yaml.safe_load(yaml_text)
        if not isinstance(parsed, dict):
            raise ValueError("Config must be a YAML mapping")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid YAML: {e}")
    CONFIG_PATH.write_text(yaml_text, encoding="utf-8")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Routes: documents
# ---------------------------------------------------------------------------

@app.get("/api/documents")
async def list_documents():
    """List all uploaded documents, grouped by doc_type subfolder."""
    if not DOCS_DIR.exists():
        return {"files": [], "subfolders": list(DOC_TYPE_SUBFOLDERS)}
    files = []
    # Walk recursively so we pick up subfolders
    for f in sorted(DOCS_DIR.rglob("*")):
        if not f.is_file() or f.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        # Determine doc_type from immediate parent folder name
        parent = f.parent
        if parent == DOCS_DIR:
            doc_type = "allgemein"
            rel_path = f.name
        else:
            folder_name = parent.name.lower()
            doc_type = folder_name if folder_name in DOC_TYPE_SUBFOLDERS else "allgemein"
            rel_path = f"{parent.name}/{f.name}"
        files.append({
            "name": f.name,
            "rel_path": rel_path,   # used for delete
            "doc_type": doc_type,
            "size": f.stat().st_size,
            "suffix": f.suffix.lower(),
        })
    return {"files": files, "subfolders": sorted(DOC_TYPE_SUBFOLDERS)}


@app.post("/api/documents")
async def upload_documents(
    files: list[UploadFile] = File(...),
    request: Request = None,
):
    """Upload documents. Pass ?doc_type=intern to place in the matching subfolder."""
    doc_type = (request.query_params.get("doc_type", "allgemein") if request else "allgemein").lower()
    if doc_type in DOC_TYPE_SUBFOLDERS:
        target_dir = DOCS_DIR / doc_type
    else:
        target_dir = DOCS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    uploaded = []
    errors = []
    for uf in files:
        if not uf.filename:
            continue
        suffix = Path(uf.filename).suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            errors.append(f"{uf.filename}: nicht unterstützter Dateityp")
            continue
        safe_name = Path(uf.filename).name  # strip any path components
        dest = target_dir / safe_name
        content = await uf.read()
        dest.write_bytes(content)
        uploaded.append({"name": safe_name, "doc_type": doc_type, "size": len(content)})
    return {"uploaded": uploaded, "errors": errors}


@app.delete("/api/documents/{rel_path:path}")
async def delete_document(rel_path: str):
    """Delete a document. rel_path may be 'filename.pdf' or 'subfolder/filename.pdf'."""
    # Prevent path traversal: only allow one level of subfolder
    parts = Path(rel_path).parts
    if len(parts) == 1:
        target = DOCS_DIR / parts[0]
    elif len(parts) == 2 and parts[0] in DOC_TYPE_SUBFOLDERS | {"allgemein"}:
        target = DOCS_DIR / parts[0] / parts[1]
    else:
        raise HTTPException(status_code=400, detail="Ungültiger Pfad")
    if not target.exists():
        raise HTTPException(status_code=404, detail="Datei nicht gefunden")
    target.unlink()
    return {"ok": True, "deleted": str(target.relative_to(DOCS_DIR))}


# ---------------------------------------------------------------------------
# Routes: reports
# ---------------------------------------------------------------------------

@app.get("/api/reports")
async def list_reports():
    if not OUT_DIR.exists():
        return {"files": []}
    files = []
    for f in sorted(OUT_DIR.iterdir(), reverse=True):
        if f.is_file():
            files.append({
                "name": f.name,
                "size": f.stat().st_size,
                "suffix": f.suffix.lower(),
                "mtime": f.stat().st_mtime,
            })
    return {"files": files}


@app.get("/api/reports/{filename}")
async def download_report(filename: str):
    safe_name = Path(filename).name
    target = OUT_DIR / safe_name
    if not target.exists():
        raise HTTPException(status_code=404, detail="Report not found")
    return FileResponse(str(target), filename=safe_name)


@app.get("/api/reports/{filename}/preview")
async def preview_report(filename: str):
    safe_name = Path(filename).name
    target = OUT_DIR / safe_name
    if not target.exists():
        raise HTTPException(status_code=404, detail="Report not found")
    if target.suffix.lower() != ".md":
        raise HTTPException(status_code=400, detail="Preview only available for .md files")
    return JSONResponse(content={"content": target.read_text(encoding="utf-8")})


# ---------------------------------------------------------------------------
# Routes: GPU monitoring
# ---------------------------------------------------------------------------

def _gpu_info() -> dict:
    """Query NVIDIA GPU info via nvidia-smi and CUDA details."""
    import subprocess

    result = {
        "available": False,
        "driver_version": None,
        "cuda_version": None,
        "gpus": [],
        "error": None,
    }

    # Query nvidia-smi for per-GPU metrics
    query_fields = (
        "index,name,utilization.gpu,utilization.memory,"
        "memory.used,memory.total,temperature.gpu,"
        "power.draw,power.limit,fan.speed"
    )
    try:
        proc = subprocess.run(
            [
                "nvidia-smi",
                f"--query-gpu={query_fields}",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode == 0:
            result["available"] = True
            for line in proc.stdout.strip().splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) < 10:
                    continue

                def _int(v: str):
                    try:
                        return int(float(v))
                    except (ValueError, TypeError):
                        return None

                def _float(v: str):
                    try:
                        return round(float(v), 1)
                    except (ValueError, TypeError):
                        return None

                result["gpus"].append({
                    "index": _int(parts[0]),
                    "name": parts[1],
                    "utilization_gpu": _int(parts[2]),
                    "utilization_memory": _int(parts[3]),
                    "memory_used_mb": _int(parts[4]),
                    "memory_total_mb": _int(parts[5]),
                    "temperature": _int(parts[6]),
                    "power_draw": _float(parts[7]),
                    "power_limit": _float(parts[8]),
                    "fan_speed": _int(parts[9]),
                })
        else:
            result["error"] = proc.stderr.strip() or "nvidia-smi fehlgeschlagen"
    except FileNotFoundError:
        result["error"] = "nvidia-smi nicht gefunden – kein NVIDIA-Treiber installiert"
    except subprocess.TimeoutExpired:
        result["error"] = "nvidia-smi Timeout"
    except Exception as exc:
        result["error"] = str(exc)

    # Driver & CUDA version from nvidia-smi main output
    if result["available"]:
        try:
            proc2 = subprocess.run(
                ["nvidia-smi", "--query", "--display=DRIVER"],
                capture_output=True, text=True, timeout=5,
            )
            for line in proc2.stdout.splitlines():
                if "Driver Version" in line:
                    result["driver_version"] = line.split(":")[-1].strip()
                if "CUDA Version" in line:
                    result["cuda_version"] = line.split(":")[-1].strip()
        except Exception:
            pass

    # Fallback: CUDA version via nvcc
    if not result["cuda_version"]:
        try:
            proc3 = subprocess.run(
                ["nvcc", "--version"], capture_output=True, text=True, timeout=5,
            )
            for line in proc3.stdout.splitlines():
                if "release" in line.lower():
                    import re
                    m = re.search(r"release\s+([\d.]+)", line, re.I)
                    if m:
                        result["cuda_version"] = m.group(1)
                        break
        except Exception:
            pass

    return result


@app.get("/api/gpu")
async def gpu_status():
    """Return live GPU / CUDA statistics."""
    return await asyncio.to_thread(_gpu_info)


# ---------------------------------------------------------------------------
# Routes: Ollama models
# ---------------------------------------------------------------------------

@app.get("/api/ollama/models")
async def ollama_models():
    try:
        cfg = _load_config()
        base_url = cfg.llm_base_url
    except Exception:
        base_url = "http://ollama:11434"
    import requests
    try:
        r = requests.get(base_url.rstrip("/") + "/api/tags", timeout=5)
        r.raise_for_status()
        models = [m["name"] for m in r.json().get("models", [])]
        return {"models": models}
    except Exception as e:
        return {"models": [], "error": str(e)}


# ---------------------------------------------------------------------------
# Routes: tasks (ingest / build / validate / wipe)
# ---------------------------------------------------------------------------

@app.get("/api/tasks/{task_id}")
async def task_status(task_id: str):
    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {
        "task_id": task.task_id,
        "name": task.name,
        "status": task.status,
        "result": task.result,
        "error": task.error,
    }


@app.get("/api/tasks/{task_id}/stream")
async def task_stream(task_id: str):
    """SSE endpoint – streams log messages until task finishes."""
    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    async def generate() -> AsyncIterator[str]:
        while True:
            try:
                msg = await asyncio.wait_for(task.messages.get(), timeout=30.0)
            except asyncio.TimeoutError:
                yield "data: {\"type\":\"ping\"}\n\n"
                continue

            if msg is None:  # sentinel → task finished
                yield f"data: {{\"type\":\"done\",\"status\":\"{task.status}\"}}\n\n"
                break
            yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering
        },
    )


# ── Ingest ─────────────────────────────────────────────────────────────────

@app.post("/api/tasks/ingest")
async def start_ingest(request: Request):
    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    reset = (body or {}).get("reset", False)
    task = _create_task("ingest")
    loop = asyncio.get_event_loop()
    asyncio.create_task(_run_ingest(task, loop, reset=reset))
    return {"task_id": task.task_id}


async def _run_ingest(task: Task, loop: asyncio.AbstractEventLoop, reset: bool = False) -> None:
    handler = _attach_queue_handler(task, loop)
    try:
        await asyncio.to_thread(_do_ingest, task, reset)
        task.status = "done"
        task.result = {"message": "Ingest abgeschlossen"}
    except Exception as e:
        task.status = "error"
        task.error = str(e)
        await task.messages.put({"type": "log", "level": "ERROR", "msg": f"Fehler: {e}"})
    finally:
        _detach_handler(handler)
        await task.messages.put(None)  # sentinel


def _do_ingest(task: Task, reset: bool) -> None:
    from tdrcreator.ingest.parser import discover_documents, parse_document
    from tdrcreator.ingest.chunker import chunk_pages
    from tdrcreator.retrieval.index import build_index, ChunkIndex

    cfg = _load_config()
    index_dir = INDEX_DIR

    if reset and index_dir.exists():
        shutil.rmtree(index_dir)

    docs = discover_documents(DOCS_DIR)
    if not docs:
        raise RuntimeError(f"Keine Dokumente in {DOCS_DIR} gefunden.")

    all_chunks = []
    for doc_path in docs:
        pages = parse_document(doc_path, use_ocr=False)
        chunks = chunk_pages(pages, chunk_size=cfg.retrieval.chunk_size, overlap=cfg.retrieval.overlap)
        all_chunks.extend(chunks)

    idx = build_index(
        chunks=all_chunks,
        model_name=cfg.embedding_model,
        index_dir=index_dir,
    )
    task.result = {"chunk_count": idx.chunk_count(), "docs": len(docs)}


# ── Build ──────────────────────────────────────────────────────────────────

@app.post("/api/tasks/build")
async def start_build(request: Request):
    body = {}
    if request.headers.get("content-type", "").startswith("application/json"):
        body = await request.json()
    skip_literature = body.get("skip_literature", False)
    task = _create_task("build")
    loop = asyncio.get_event_loop()
    asyncio.create_task(_run_build(task, loop, skip_literature=skip_literature))
    return {"task_id": task.task_id}


async def _run_build(task: Task, loop: asyncio.AbstractEventLoop, skip_literature: bool = False) -> None:
    handler = _attach_queue_handler(task, loop)
    try:
        await asyncio.to_thread(_do_build, task, skip_literature)
        task.status = "done"
    except Exception as e:
        task.status = "error"
        task.error = str(e)
        await task.messages.put({"type": "log", "level": "ERROR", "msg": f"Fehler: {e}"})
    finally:
        _detach_handler(handler)
        await task.messages.put(None)


def _do_build(task: Task, skip_literature: bool) -> None:
    from tdrcreator.retrieval.index import ChunkIndex
    from tdrcreator.literature.guard import QueryGuard
    from tdrcreator.literature.searcher import search_literature
    from tdrcreator.citations.bibtex import export_bibtex, export_csl_json
    from tdrcreator.report.builder import build_report
    from tdrcreator.report.exporter import export_markdown, export_docx, export_pdf

    cfg = _load_config()

    if not ChunkIndex.exists(INDEX_DIR):
        raise RuntimeError("Kein Index gefunden – bitte zuerst Ingest ausführen.")

    idx = ChunkIndex.load(INDEX_DIR)

    # Literature
    ext_refs = []
    if cfg.literature.enabled and not skip_literature and cfg.privacy.allow_network_for_literature:
        guard = QueryGuard(enabled=False, auto_yes=True)  # no interactive prompts in webapp
        keywords = cfg.literature.allowed_keywords or [cfg.topic]
        ext_refs = search_literature(
            queries=keywords,
            sources=cfg.literature.sources,
            max_papers=cfg.literature.max_papers,
            year_range=cfg.literature.year_range,
            allow_network=cfg.privacy.allow_network_for_literature,
            guard=guard,
        )

    artifact = build_report(config=cfg, index=idx, ext_refs=ext_refs)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    safe_title = cfg.project_title.replace(" ", "_").replace("/", "-")

    if cfg.output.md:
        export_markdown(artifact.full_markdown, OUT_DIR / f"{safe_title}.md")
    if cfg.output.docx:
        export_docx(artifact.full_markdown, OUT_DIR / f"{safe_title}.docx")
    if cfg.output.pdf:
        export_pdf(artifact.full_markdown, OUT_DIR / f"{safe_title}.pdf")

    if ext_refs:
        export_bibtex(ext_refs, OUT_DIR / "references.bib")
        export_csl_json(ext_refs, OUT_DIR / "references.json")

    task.result = {"word_count": artifact.word_count, "reports": safe_title}


# ── Validate ───────────────────────────────────────────────────────────────

@app.post("/api/tasks/validate")
async def start_validate():
    task = _create_task("validate")
    loop = asyncio.get_event_loop()
    asyncio.create_task(_run_validate(task, loop))
    return {"task_id": task.task_id}


async def _run_validate(task: Task, loop: asyncio.AbstractEventLoop) -> None:
    handler = _attach_queue_handler(task, loop)
    try:
        await asyncio.to_thread(_do_validate, task)
        task.status = "done"
    except Exception as e:
        task.status = "error"
        task.error = str(e)
        await task.messages.put({"type": "log", "level": "ERROR", "msg": f"Fehler: {e}"})
    finally:
        _detach_handler(handler)
        await task.messages.put(None)


def _do_validate(task: Task) -> None:
    from tdrcreator.retrieval.index import ChunkIndex
    from tdrcreator.citations.validator import validate

    cfg = _load_config()
    safe_title = cfg.project_title.replace(" ", "_").replace("/", "-")
    report_path = OUT_DIR / f"{safe_title}.md"

    if not report_path.exists():
        # Try to find any .md in out/
        md_files = list(OUT_DIR.glob("*.md")) if OUT_DIR.exists() else []
        if not md_files:
            raise RuntimeError("Kein Report gefunden – bitte zuerst Build ausführen.")
        report_path = md_files[0]

    report_text = report_path.read_text(encoding="utf-8")
    known_chunk_ids: set[str] = set()
    if ChunkIndex.exists(INDEX_DIR):
        idx = ChunkIndex.load(INDEX_DIR)
        known_chunk_ids = {c.chunk_id for c in idx.all_chunks()}

    result = validate(
        report_text=report_text,
        known_chunk_ids=known_chunk_ids,
        known_ref_ids=set(),
        scientific_mode=cfg.scientific_mode,
        strict=False,
    )
    task.result = {
        "ok": result.ok,
        "uncited": len(result.uncited_paragraphs),
        "unknown_src": len(result.unknown_src_ids),
        "messages": result.messages,
    }
    if not result.ok:
        for msg in result.messages:
            import asyncio as _as
            # Can't await here; use logging so the handler picks it up
            logging.getLogger("tdrcreator.validate").warning(msg)


# ── Pitch ──────────────────────────────────────────────────────────────────

@app.post("/api/tasks/pitch")
async def start_pitch():
    task = _create_task("pitch")
    loop = asyncio.get_event_loop()
    asyncio.create_task(_run_pitch(task, loop))
    return {"task_id": task.task_id}


async def _run_pitch(task: Task, loop: asyncio.AbstractEventLoop) -> None:
    handler = _attach_queue_handler(task, loop)
    try:
        await asyncio.to_thread(_do_pitch, task)
        task.status = "done"
    except Exception as e:
        task.status = "error"
        task.error = str(e)
        await task.messages.put({"type": "log", "level": "ERROR", "msg": f"Fehler: {e}"})
    finally:
        _detach_handler(handler)
        await task.messages.put(None)


def _do_pitch(task: Task) -> None:
    from tdrcreator.retrieval.index import ChunkIndex
    from tdrcreator.report.builder import build_pitch
    from tdrcreator.report.exporter import export_markdown, export_docx

    cfg = _load_config()

    if not ChunkIndex.exists(INDEX_DIR):
        raise RuntimeError("Kein Index gefunden – bitte zuerst Ingest ausführen.")

    idx = ChunkIndex.load(INDEX_DIR)
    artifact = build_pitch(config=cfg, index=idx, ext_refs=[])

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    safe_title = cfg.project_title.replace(" ", "_").replace("/", "-")
    pitch_path = OUT_DIR / f"{safe_title}_Pitch.md"
    export_markdown(artifact.markdown, pitch_path)

    if cfg.output.docx:
        export_docx(artifact.markdown, OUT_DIR / f"{safe_title}_Pitch.docx")

    task.result = {"word_count": artifact.word_count, "file": pitch_path.name}


# ── Wipe index ─────────────────────────────────────────────────────────────

@app.post("/api/tasks/wipe-index")
async def wipe_index():
    if INDEX_DIR.exists():
        shutil.rmtree(INDEX_DIR)
    return {"ok": True}


# ── Wipe all ───────────────────────────────────────────────────────────────

@app.post("/api/tasks/wipe-all")
async def wipe_all():
    for d in (INDEX_DIR, OUT_DIR):
        if d.exists():
            shutil.rmtree(d)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Routes: Design Editor (Entwürfe)
# ---------------------------------------------------------------------------

ENTWURF_DIR = DOCS_DIR / "entwurf"


@app.get("/api/entwuerfe")
async def list_entwuerfe():
    """List all draft documents in the entwurf folder."""
    ENTWURF_DIR.mkdir(parents=True, exist_ok=True)
    files = []
    for f in sorted(ENTWURF_DIR.iterdir()):
        if f.is_file() and f.suffix.lower() in {".md", ".txt"}:
            files.append({
                "name": f.name,
                "size": f.stat().st_size,
                "mtime": f.stat().st_mtime,
            })
    return {"files": files}


@app.post("/api/editor/export-docx")
async def export_editor_docx(request: Request):
    """Export editor content as DOCX download."""
    body = await request.json()
    content: str = body.get("content", "")
    filename: str = body.get("filename", "entwurf")
    if not content.strip():
        raise HTTPException(status_code=400, detail="Kein Inhalt zum Exportieren")
    import re as _re
    safe_name = _re.sub(r'[^\w\-]', '_', Path(filename).stem)
    out_path = OUT_DIR / f"_draft_{safe_name}.docx"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        from tdrcreator.report.exporter import export_docx
        await asyncio.to_thread(export_docx, content, out_path)
        return FileResponse(
            path=str(out_path),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename=f"{safe_name}.docx",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export fehlgeschlagen: {e}")


@app.get("/api/entwuerfe/{filename}")
async def get_entwurf(filename: str):
    """Read a single draft document."""
    safe_name = Path(filename).name
    target = ENTWURF_DIR / safe_name
    if not target.exists():
        raise HTTPException(status_code=404, detail="Entwurf nicht gefunden")
    return {"name": safe_name, "content": target.read_text(encoding="utf-8")}


@app.post("/api/entwuerfe/{filename}")
async def save_entwurf(filename: str, request: Request):
    """Create or update a draft document."""
    body = await request.json()
    content: str = body.get("content", "")
    safe_name = Path(filename).name
    if not safe_name.endswith((".md", ".txt")):
        safe_name += ".md"
    ENTWURF_DIR.mkdir(parents=True, exist_ok=True)
    target = ENTWURF_DIR / safe_name
    target.write_text(content, encoding="utf-8")
    return {"ok": True, "name": safe_name, "size": len(content.encode("utf-8"))}


@app.delete("/api/entwuerfe/{filename}")
async def delete_entwurf(filename: str):
    """Delete a draft document."""
    safe_name = Path(filename).name
    target = ENTWURF_DIR / safe_name
    if not target.exists():
        raise HTTPException(status_code=404, detail="Entwurf nicht gefunden")
    target.unlink()
    return {"ok": True, "deleted": safe_name}


@app.post("/api/entwuerfe/{filename}/llm-assist")
async def llm_assist_entwurf(filename: str, request: Request):
    """Use the LLM to modify/enhance a draft based on user instructions."""
    body = await request.json()
    instruction: str = body.get("instruction", "").strip()
    current_content: str = body.get("content", "")
    provider: str = body.get("provider", "ollama")
    ext_api_key: str = body.get("api_key", "")
    ext_model: str = body.get("model", "")
    if not instruction:
        raise HTTPException(status_code=400, detail="Keine Anweisung angegeben")
    if provider not in ("ollama", "openai", "anthropic"):
        raise HTTPException(status_code=400, detail="Ungültiger Anbieter")
    if provider != "ollama" and not ext_api_key:
        raise HTTPException(status_code=400, detail="API-Key erforderlich für externen Anbieter")

    task = _create_task("llm-assist")
    loop = asyncio.get_event_loop()
    asyncio.create_task(_run_llm_assist(
        task, loop, filename, instruction, current_content,
        provider, ext_api_key, ext_model
    ))
    return {"task_id": task.task_id}


async def _run_llm_assist(
    task: Task,
    loop: asyncio.AbstractEventLoop,
    filename: str,
    instruction: str,
    current_content: str,
    provider: str = "ollama",
    ext_api_key: str = "",
    ext_model: str = "",
) -> None:
    handler = _attach_queue_handler(task, loop)
    try:
        result_text = await asyncio.to_thread(
            _do_llm_assist, task, instruction, current_content,
            provider, ext_api_key, ext_model
        )
        task.status = "done"
        task.result = {"content": result_text}
    except Exception as e:
        task.status = "error"
        task.error = str(e)
        await task.messages.put({"type": "log", "level": "ERROR", "msg": f"Fehler: {e}"})
    finally:
        _detach_handler(handler)
        await task.messages.put(None)


def _do_llm_assist(
    task: Task, instruction: str, current_content: str,
    provider: str = "ollama", ext_api_key: str = "", ext_model: str = "",
) -> str:
    cfg = _load_config()

    if current_content.strip():
        prompt = f"""Du bist ein technischer Redakteur und Assistent.

Der Benutzer arbeitet an einem Entwurf (Dokument). Hier ist der aktuelle Inhalt:

=== AKTUELLER ENTWURF ===
{current_content}
=== ENDE ENTWURF ===

Der Benutzer gibt dir folgende Anweisung:
{instruction}

Bitte führe die Anweisung aus und gib den vollständigen, aktualisierten Entwurf zurück.
Gib NUR den aktualisierten Dokumentinhalt zurück, ohne zusätzliche Erklärungen oder Kommentare.
Behalte das Markdown-Format bei."""
    else:
        prompt = f"""Du bist ein technischer Redakteur und Assistent.

Der Benutzer möchte einen neuen Entwurf erstellen. Er gibt dir folgende Anweisung:
{instruction}

Bitte erstelle den Entwurf basierend auf der Anweisung.
Gib NUR den Dokumentinhalt zurück, ohne zusätzliche Erklärungen.
Verwende Markdown-Format."""

    logging.getLogger("tdrcreator").info(
        f"LLM-Assistent ({provider}): Anweisung wird verarbeitet ({len(instruction)} Zeichen)…"
    )

    if provider == "ollama":
        from tdrcreator.report.llm import generate
        result = generate(
            prompt=prompt,
            base_url=cfg.llm_base_url,
            model=cfg.llm_model,
            temperature=cfg.llm_temperature,
            timeout=cfg.llm_timeout,
        )
    elif provider == "openai":
        result = _call_openai(prompt, ext_api_key, ext_model or "gpt-4o", cfg.llm_temperature)
    elif provider == "anthropic":
        result = _call_anthropic(prompt, ext_api_key, ext_model or "claude-sonnet-4-20250514", cfg.llm_temperature)
    else:
        raise ValueError(f"Unbekannter Anbieter: {provider}")

    logging.getLogger("tdrcreator").info(
        f"LLM-Assistent ({provider}): Antwort erhalten ({len(result)} Zeichen)"
    )
    return result


# ---------------------------------------------------------------------------
# External LLM connectors (for editor assist only — user provides API key)
# ---------------------------------------------------------------------------

def _call_openai(prompt: str, api_key: str, model: str, temperature: float) -> str:
    """Call OpenAI Chat Completions API."""
    import requests as _req
    resp = _req.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
        },
        timeout=180,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _call_anthropic(prompt: str, api_key: str, model: str, temperature: float) -> str:
    """Call Anthropic Messages API."""
    import requests as _req
    resp = _req.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": 8192,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
        },
        timeout=180,
    )
    resp.raise_for_status()
    return resp.json()["content"][0]["text"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_task(name: str) -> Task:
    task_id = str(uuid.uuid4())
    task = Task(task_id=task_id, name=name)
    _tasks[task_id] = task
    # Prune old tasks (keep last 20)
    if len(_tasks) > 20:
        oldest = list(_tasks.keys())[0]
        del _tasks[oldest]
    return task


# ---------------------------------------------------------------------------
# Entry point (for `python -m tdrcreator.webapp.api`)
# ---------------------------------------------------------------------------

def main() -> None:
    import uvicorn
    host = os.getenv("TDR_HOST", "0.0.0.0")
    port = int(os.getenv("TDR_PORT", "8000"))
    uvicorn.run("tdrcreator.webapp.api:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
