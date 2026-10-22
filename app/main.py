"""Local, authenticated creative experiment workflow. No external calls by default."""

import csv
import hashlib
import hmac
import io
import json
import math
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from . import db

MAX_VIDEO = 50 * 1024 * 1024
MAX_CSV = 1024 * 1024
POOL = ThreadPoolExecutor(max_workers=2)
LOCK = threading.Lock()
WEB = Path(__file__).resolve().parents[1] / "web"


@asynccontextmanager
async def lifespan(app):
    db.init()
    with db.connect() as c:
        for row in c.execute(
            "SELECT wid,payload FROM records WHERE kind='operation'"
        ).fetchall():
            op = json.loads(row["payload"])
            if op["status"] in ("pending", "running"):
                op.update(
                    status="interrupted",
                    error="Server restarted. Outcome unknown; inspect saved artifacts before retrying.",
                )
                db.save(c, row["wid"], "operation", op)
    yield


app = FastAPI(title="Creative Experiments", lifespan=lifespan)


@app.middleware("http")
async def boundary(request, call_next):
    if request.method in ("POST", "PATCH", "PUT", "DELETE"):
        origin = request.headers.get("origin")
        if origin and origin != str(request.base_url).rstrip("/"):
            return JSONResponse({"detail": "Cross-origin writes are not allowed"}, 403)
        length = request.headers.get("content-length")
        if (
            request.headers.get("content-type", "").startswith("multipart/")
            and not length
        ):
            return JSONResponse(
                {"detail": "Uploads require a bounded Content-Length"}, 411
            )
        if length and (not length.isdigit() or int(length) > MAX_VIDEO + 1024 * 1024):
            return JSONResponse({"detail": "Request exceeds 50 MiB media limit"}, 413)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    )
    return response


@app.exception_handler(ValueError)
async def bad_input(request, exc):
    return JSONResponse({"detail": str(exc)}, 422)


class Body(BaseModel):
    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, allow_inf_nan=False
    )


class Credentials(Body):
    email: str = Field(
        min_length=3, max_length=180, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$"
    )
    password: str = Field(min_length=10, max_length=128)


class Brand(Body):
    name: str = Field(min_length=1, max_length=100)
    product: str = Field(default="", max_length=2000)
    audience: str = Field(default="", max_length=1000)
    goal: str = Field(default="", max_length=1000)


class AnalysisRequest(Body):
    mode: Literal["local", "openai"] = "local"


class Experiment(Body):
    title: str = Field(min_length=1, max_length=200)
    hypothesis: str = Field(min_length=1, max_length=3000)
    baseline_id: str
    recommendation_id: str | None = None
    change: str = Field(min_length=1, max_length=2000)
    preserve: list[str] = Field(default_factory=list, max_length=20)
    metric: Literal["retention_3s"] = "retention_3s"
    threshold_pp: float = Field(default=5, ge=0, le=100)
    min_views: int = Field(default=100, ge=1, le=100000000)
    window_days: int = Field(default=7, ge=1, le=90)
    limitations: list[str] = Field(default_factory=list, max_length=20)


class ExperimentPatch(Body):
    hypothesis: str | None = Field(default=None, min_length=1, max_length=3000)
    threshold_pp: float | None = Field(default=None, ge=0, le=100)
    min_views: int | None = Field(default=None, ge=1, le=100000000)
    window_days: int | None = Field(default=None, ge=1, le=90)
    status: Literal["draft", "ready", "awaiting", "completed"] | None = None


# Login endpoints are intended for a loopback-only development server.
def user(request):
    token = request.cookies.get("ce_session", "")
    digest = hashlib.sha256(token.encode()).hexdigest()
    with db.connect() as c:
        r = c.execute(
            "SELECT u.id,u.email FROM users u JOIN sessions s ON s.user_id=u.id WHERE s.token=? AND s.expires>?",
            (digest, time.time()),
        ).fetchone()
    if not r:
        raise HTTPException(401, "Sign in to continue")
    return dict(r)


def owner(request, wid):
    u = user(request)
    with db.connect() as c:
        r = c.execute(
            "SELECT payload FROM workspaces WHERE id=? AND owner=?", (wid, u["id"])
        ).fetchone()
    if not r:
        raise HTTPException(404, "Workspace not found")
    return json.loads(r[0])


def get(c, wid, kind, rid):
    value = db.record(c, wid, kind, rid)
    if value is None:
        raise HTTPException(404, f"{kind.capitalize()} not found")
    return value


def session(response, userid):
    token = db.uid() + db.uid()
    with db.connect() as c:
        c.execute(
            "INSERT INTO sessions VALUES(?,?,?)",
            (hashlib.sha256(token.encode()).hexdigest(), userid, time.time() + 86400),
        )
    response.set_cookie(
        "ce_session",
        token,
        max_age=86400,
        httponly=True,
        samesite="strict",
        secure=False,
    )


@app.post("/api/register")
def register(body: Credentials, response: Response):
    with db.connect() as c:
        if c.execute(
            "SELECT 1 FROM users WHERE email=?", (body.email.lower(),)
        ).fetchone():
            raise HTTPException(409, "Email already registered")
        value = {"id": db.uid(), "email": body.email.lower()}
        c.execute(
            "INSERT INTO users VALUES(?,?,?)",
            (value["id"], value["email"], db.password(body.password)),
        )
    session(response, value["id"])
    return value


@app.post("/api/login")
def login(body: Credentials, response: Response):
    with db.connect() as c:
        r = c.execute(
            "SELECT * FROM users WHERE email=?", (body.email.lower(),)
        ).fetchone()
    if not r or not hmac.compare_digest(
        db.password(body.password, r["password"].split(":")[0]), r["password"]
    ):
        raise HTTPException(401, "Email or password is incorrect")
    session(response, r["id"])
    return {"id": r["id"], "email": r["email"]}


@app.post("/api/logout")
def logout(request: Request, response: Response):
    with db.connect() as c:
        c.execute(
            "DELETE FROM sessions WHERE token=?",
            (
                hashlib.sha256(
                    request.cookies.get("ce_session", "").encode()
                ).hexdigest(),
            ),
        )
    response.delete_cookie("ce_session")
    return {"ok": True}


@app.get("/api/me")
def me(request: Request):
    return user(request)


@app.get("/api/workspaces")
def brands(request: Request):
    u = user(request)
    with db.connect() as c:
        return [
            json.loads(r[0])
            for r in c.execute(
                "SELECT payload FROM workspaces WHERE owner=?", (u["id"],)
            )
        ]


@app.post("/api/workspaces")
def create_brand(request: Request, body: Brand):
    u = user(request)
    v = {"id": db.uid(), **body.model_dump(), "synthetic": False}
    with db.connect() as c:
        c.execute(
            "INSERT INTO workspaces VALUES(?,?,?)", (v["id"], u["id"], db.pack(v))
        )
    return v


def enrich_video(v, wid, metrics):
    return {k: x for k, x in v.items() if k != "path"} | {
        "media_url": f'/api/workspaces/{wid}/videos/{v["id"]}/media',
        "metrics": [m for m in metrics if m["video_id"] == v["id"]],
    }


@app.get("/api/workspaces/{wid}/videos")
def videos(request: Request, wid: str):
    owner(request, wid)
    with db.connect() as c:
        return [
            enrich_video(v, wid, db.rows(c, wid, "metric"))
            for v in db.rows(c, wid, "video")
        ]


async def store_upload(file, folder, limit, suffix):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (db.uid() + suffix)
    size = 0
    try:
        with path.open("xb") as out:
            while chunk := await file.read(65536):
                size += len(chunk)
                if size > limit:
                    raise HTTPException(
                        413, f"File exceeds {limit//1024//1024} MiB limit"
                    )
                out.write(chunk)
        if not size:
            raise HTTPException(422, "File is empty")
        return path
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    finally:
        await file.close()


@app.post("/api/workspaces/{wid}/videos")
async def upload_video(
    request: Request,
    wid: str,
    file: UploadFile = File(...),
    title: str = Form("Untitled video"),
):
    brand = owner(request, wid)
    if brand["synthetic"]:
        raise HTTPException(
            409,
            "Upload user videos into a new workspace, separate from synthetic demo data",
        )
    if not file.filename or Path(file.filename).suffix.lower() != ".mp4":
        raise HTTPException(422, "Only MP4 uploads are supported")
    if len(title) > 200:
        raise HTTPException(422, "Title exceeds 200 characters")
    path = await store_upload(file, db.ROOT / wid, MAX_VIDEO, ".mp4")
    from .media import probe

    try:
        metadata = probe(path)
    except Exception as e:
        path.unlink(missing_ok=True)
        raise HTTPException(422, "Video cannot be processed: " + str(e)[:300])
    value = {
        "id": db.uid(),
        "title": title,
        "filename": Path(file.filename).name,
        "path": str(path),
        "synthetic": False,
        "analysis": None,
        **metadata,
        "created_at": db.now(),
    }
    with db.connect() as c:
        db.save(c, wid, "video", value)
        c.execute("DELETE FROM records WHERE wid=? AND kind='recommendation'", (wid,))
    return enrich_video(value, wid, [])


@app.get("/api/workspaces/{wid}/videos/{vid}/media")
def media(request: Request, wid: str, vid: str):
    owner(request, wid)
    with db.connect() as c:
        v = get(c, wid, "video", vid)
    return FileResponse(v["path"], media_type="video/mp4")


@app.get("/api/workspaces/{wid}/operations")
def operations(request: Request, wid: str):
    owner(request, wid)
    with db.connect() as c:
        return db.rows(c, wid, "operation")


def launch(wid, kind, inputs, work):
    with LOCK, db.connect() as c:
        if any(
            x["status"] in ("pending", "running") for x in db.rows(c, wid, "operation")
        ):
            raise HTTPException(409, "A workspace operation is already running")
        op = {
            "id": db.uid(),
            "kind": kind,
            "status": "pending",
            "input": inputs,
            "result": None,
            "error": None,
            "model": None,
            "prompt_version": None,
            "duration_ms": None,
            "cost_usd": None,
            "created_at": db.now(),
        }
        db.save(c, wid, "operation", op)

    def execute():
        begin = time.monotonic()
        op["status"] = "running"
        with db.connect() as c:
            db.save(c, wid, "operation", op)
        try:
            op["result"] = work(op)
            op["status"] = "completed"
        except Exception as e:
            op["status"] = "failed"
            op["error"] = str(e)[:1000].replace(
                os.environ.get("OPENAI_API_KEY") or "__NO_KEY__", "[redacted]"
            )
            if op.get("reservation_usd"):
                op["budget_halted"] = True
        op["duration_ms"] = round((time.monotonic() - begin) * 1000)
        with db.connect() as c:
            db.save(c, wid, "operation", op)

    POOL.submit(execute)
    return op.copy()


@app.post("/api/workspaces/{wid}/videos/{vid}/analyze")
def analyze(request: Request, wid: str, vid: str, body: AnalysisRequest):
    brand = owner(request, wid)
    with db.connect() as c:
        v = get(c, wid, "video", vid)
    if body.mode == "openai" and not os.environ.get("CE_OPENAI_APPROVED_BUDGET_USD"):
        raise HTTPException(
            403,
            "Live API is disabled. A separate model and spending authorization is required.",
        )

    def work(op):
        from .media import extract_frames
        from .provider import analyze as vision

        if brand["synthetic"] and v["analysis"] is not None:
            result = v["analysis"]
            op["model"] = "synthetic fixture"
            op["prompt_version"] = "fixture-v1"
            op["cost_usd"] = 0
        else:
            frames = extract_frames(
                Path(v["path"]), db.ROOT / wid / (op["id"] + "-frames")
            )
            metadata = {
                k: v[k] for k in ("duration", "width", "height", "fps", "has_audio")
            }
            if body.mode == "local":
                result = {
                    "mode": "local",
                    "model": None,
                    "prompt_version": "local-v1",
                    "measured": metadata,
                    "hook_category": "unknown",
                    "segments": [
                        {
                            "start": f["time"],
                            "end": min(v["duration"], f["time"] + 1),
                            "kind": "scene",
                            "text": "Sampled frame; semantic interpretation unavailable in local mode",
                            "origin": "measurement",
                            "frame_index": f["index"],
                        }
                        for f in frames
                    ],
                    "limitations": [
                        "Local mode measures media and samples frames. It does not recognize hooks, text, products or speech."
                    ],
                    "speech_status": "not_transcribed",
                }
                op["cost_usd"] = 0
            else:
                reserve(op, wid)
                result, usage = vision(
                    Path(v["path"]),
                    metadata,
                    frames,
                    authorized=True,
                    transcribe=os.environ.get("CE_APPROVED_TRANSCRIPTION_MODEL")
                    == "whisper-1",
                )
                op.update(usage)
                reconcile(op)

            op["model"] = result.get("model")
            op["prompt_version"] = result["prompt_version"]
        with db.connect() as c:
            updated = get(c, wid, "video", vid)
            updated["analysis"] = result
            db.save(c, wid, "video", updated)
            c.execute(
                "DELETE FROM records WHERE wid=? AND kind='recommendation'", (wid,)
            )
        return result

    return launch(wid, "analysis", {"video_id": vid, "mode": body.mode}, work)


@app.post("/api/workspaces/{wid}/import")
async def import_csv(request: Request, wid: str, file: UploadFile = File(...)):
    owner(request, wid)
    raw = await file.read(MAX_CSV + 1)
    await file.close()
    if len(raw) > MAX_CSV:
        raise HTTPException(413, "CSV exceeds 1 MiB")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(422, "CSV must be UTF-8")
    from .research import validate_csv

    with db.connect() as c:
        c.execute("BEGIN IMMEDIATE")
        new = validate_csv(text, db.rows(c, wid, "video"), db.rows(c, wid, "metric"))
        if new:
            c.execute(
                "DELETE FROM records WHERE wid=? AND kind='recommendation'", (wid,)
            )
        for row in new:
            db.save(c, wid, "metric", dict(row, id=db.uid(), imported_at=db.now()))
    total = len(list(csv.DictReader(io.StringIO(text))))
    return {"inserted": len(new), "duplicate": total - len(new), "rows": new}


@app.get("/api/workspaces/{wid}/csv-template")
def csv_template(request: Request, wid: str):
    owner(request, wid)
    from .research import CSV_COLUMNS

    with db.connect() as c:
        items = db.rows(c, wid, "video")
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    if items:
        writer.writerow(
            dict(
                publication_id="replace-with-post-id",
                video_id=items[0]["id"],
                platform="instagram",
                traffic="organic",
                source="manual-platform-export",
                period_start="2026-10-01",
                period_end="2026-10-08",
                views="",
                retention_3s="",
                retention_unit="fraction",
            )
        )
    return Response(
        out.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="metrics-template.csv"'},
    )


@app.get("/api/workspaces/{wid}/recommendations")
def recommendations(request: Request, wid: str):
    owner(request, wid)
    from .research import recommend

    with db.connect() as c:
        return db.rows(c, wid, "recommendation") or recommend(
            db.rows(c, wid, "video"), db.rows(c, wid, "metric")
        )


@app.get("/api/workspaces/{wid}/experiments")
def experiments(request: Request, wid: str):
    owner(request, wid)
    with db.connect() as c:
        return db.rows(c, wid, "experiment")


@app.post("/api/workspaces/{wid}/experiments")
def create_experiment(request: Request, wid: str, body: Experiment):
    owner(request, wid)
    from .research import gen_brief

    with db.connect() as c:
        get(c, wid, "video", body.baseline_id)
        value = {
            "id": db.uid(),
            **body.model_dump(),
            "variant_id": None,
            "status": "draft",
            "revision": 1,
            "created_at": db.now(),
            "result": None,
            "history": [],
            "frozen_criteria": None,
        }
        from .research import recommend

        choices = db.rows(c, wid, "recommendation") or recommend(
            db.rows(c, wid, "video"), db.rows(c, wid, "metric")
        )
        value["source_snapshot"] = next(
            (r for r in choices if r["id"] == body.recommendation_id), None
        )
        if body.recommendation_id and value["source_snapshot"] is None:
            raise HTTPException(
                422, "Recommendation no longer available; refresh sources"
            )
        value["generation_brief"] = gen_brief(value)
        value["history"].append(
            {
                "at": db.now(),
                "action": "created",
                "revision": 1,
                "snapshot": body.model_dump(),
            }
        )
        db.save(c, wid, "experiment", value)
    return value


@app.get("/api/workspaces/{wid}/experiments/{eid}")
def experiment(request: Request, wid: str, eid: str):
    owner(request, wid)
    with db.connect() as c:
        return get(c, wid, "experiment", eid)


@app.patch("/api/workspaces/{wid}/experiments/{eid}")
def update_experiment(request: Request, wid: str, eid: str, body: ExperimentPatch):
    owner(request, wid)
    changes = body.model_dump(exclude_none=True)
    from .research import gen_brief

    with db.connect() as c:
        c.execute("BEGIN IMMEDIATE")
        value = get(c, wid, "experiment", eid)
        target = changes.get("status")
        status = value["status"]
        if target and target != status:
            if (status, target) not in [("draft", "ready"), ("ready", "awaiting")]:
                raise HTTPException(
                    409, "Use the next status; completion requires evaluation"
                )
            if not value["variant_id"]:
                raise HTTPException(409, "Prepare an edited version first")
        value.update(changes)
        value["revision"] += 1
        value["generation_brief"] = gen_brief(value)
        if target == "awaiting" and status != "awaiting":
            value["results_present_at_freeze"] = any(
                m["video_id"] == value["variant_id"] for m in db.rows(c, wid, "metric")
            )
        if target == "awaiting" and status != "awaiting":
            value["frozen_criteria"] = {
                k: value[k]
                for k in (
                    "hypothesis",
                    "threshold_pp",
                    "min_views",
                    "window_days",
                    "metric",
                    "revision",
                )
            }
        value["history"].append(
            {
                "at": db.now(),
                "action": (
                    "criteria_edited_after_freeze"
                    if value["frozen_criteria"] and not target
                    else "updated"
                ),
                "revision": value["revision"],
                "changes": changes,
                "frozen_criteria": value["frozen_criteria"],
            }
        )
        db.save(c, wid, "experiment", value)
    return value


@app.post("/api/workspaces/{wid}/experiments/{eid}/edit")
async def edit_video(
    request: Request,
    wid: str,
    eid: str,
    file: UploadFile = File(...),
    start: float = Form(...),
    end: float = Form(...),
):
    brand = owner(request, wid)
    with db.connect() as c:
        exp = get(c, wid, "experiment", eid)
        source = get(c, wid, "video", exp["baseline_id"])
    if exp["status"] != "draft":
        raise HTTPException(409, "Editing is only allowed in draft")
    if (
        not math.isfinite(start)
        or not math.isfinite(end)
        or not 0 <= start < end <= source["duration"]
    ):
        raise HTTPException(422, "Invalid replacement interval")
    if not file.filename or Path(file.filename).suffix.lower() != ".mp4":
        raise HTTPException(422, "Replacement must be MP4")
    replacement = await store_upload(file, db.ROOT / wid, MAX_VIDEO, ".mp4")
    if brand["synthetic"]:
        fixture = db.ROOT / "demo-coffee" / "replacement.mp4"
        if (
            not fixture.is_file()
            or hashlib.sha256(replacement.read_bytes()).digest()
            != hashlib.sha256(fixture.read_bytes()).digest()
        ):
            replacement.unlink(missing_ok=True)
            raise HTTPException(
                409,
                "Synthetic demo edits require the supplied demo alternative fragment. Create an ordinary workspace for your own material.",
            )

    def work(op):
        from .media import replace_segment, probe

        variant_id = db.uid()
        out = db.ROOT / wid / (variant_id + ".mp4")
        report = replace_segment(Path(source["path"]), replacement, start, end, out)
        v = {
            "id": variant_id,
            "title": exp["title"] + " · edited version",
            "filename": out.name,
            "path": str(out),
            "synthetic": source["synthetic"],
            "analysis": None,
            "created_at": db.now(),
            **probe(out),
        }
        # Only originally authored sources have fixture annotations; edited variants need fresh analysis.
        with db.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            latest = get(c, wid, "experiment", eid)
            if latest["status"] != "draft":
                raise ValueError("Experiment status changed while editing")
            db.save(c, wid, "video", v)
            latest["variant_id"] = variant_id
            latest["edit_report"] = report
            latest["edit_start"] = start
            latest["edit_end"] = end
            latest["revision"] += 1
            from .research import gen_brief

            latest["generation_brief"] = gen_brief(latest)
            latest["history"].append(
                {
                    "at": db.now(),
                    "action": "segment_replaced",
                    "revision": latest["revision"],
                    "start": start,
                    "end": end,
                    "variant_id": variant_id,
                    "report": report,
                }
            )
            db.save(c, wid, "experiment", latest)
        op["cost_usd"] = 0
        return {"video_id": variant_id, "report": report}

    try:
        return launch(
            wid,
            "edit",
            {
                "experiment_id": eid,
                "start": start,
                "end": end,
                "replacement_sha256": hashlib.sha256(
                    replacement.read_bytes()
                ).hexdigest(),
            },
            work,
        )
    except BaseException:
        replacement.unlink(missing_ok=True)
        raise


@app.post("/api/workspaces/{wid}/experiments/{eid}/evaluate")
def evaluate_experiment(request: Request, wid: str, eid: str):
    owner(request, wid)
    from .research import evaluate

    with db.connect() as c:
        c.execute("BEGIN IMMEDIATE")
        exp = get(c, wid, "experiment", eid)
        if exp["status"] not in ("awaiting", "completed"):
            raise HTTPException(409, "Move experiment to awaiting results first")
        metrics = db.rows(c, wid, "metric")
        baseline = [m for m in metrics if m["video_id"] == exp["baseline_id"]]
        variant = [m for m in metrics if m["video_id"] == exp["variant_id"]]
        result = evaluate(exp, baseline, variant)
        if exp.get("results_present_at_freeze"):
            result["limitations"].append(
                "Variant results were already present when criteria were frozen; this is a retrospective criterion, not preregistration."
            )
        result["evaluated_at"] = db.now()
        result["synthetic"] = get(c, wid, "video", exp["baseline_id"])["synthetic"]
        exp["result"] = result
        exp["status"] = "completed"
        exp["history"].append(
            {
                "at": db.now(),
                "action": "evaluated",
                "criteria_revision": exp["frozen_criteria"]["revision"],
                "result": result,
            }
        )
        db.save(c, wid, "experiment", exp)
    return result


@app.get("/api/workspaces/{wid}/knowledge")
def knowledge(request: Request, wid: str):
    owner(request, wid)
    with db.connect() as c:
        return [e for e in db.rows(c, wid, "experiment") if e["result"] is not None]


@app.get("/")
def home():
    return FileResponse(WEB / "index.html")


app.mount("/static", StaticFiles(directory=WEB), name="static")


@app.get("/api/demo/replacement")
def demo_replacement(request: Request):
    user(request)
    path = db.ROOT / "demo-coffee" / "replacement.mp4"
    if not path.exists():
        raise HTTPException(404, "Run python -m app.demo first")
    return FileResponse(
        path, media_type="video/mp4", filename="synthetic-replacement.mp4"
    )


@app.get("/api/demo/sample-video")
def demo_sample(request: Request):
    user(request)
    path = db.ROOT / "demo-coffee" / "demo-video-1.mp4"
    if not path.exists():
        raise HTTPException(404, "Run python -m app.demo first")
    return FileResponse(path, media_type="video/mp4", filename="synthetic-sample.mp4")


@app.get("/api/workspaces/{wid}/experiments/{eid}/csv-template")
def experiment_csv(request: Request, wid: str, eid: str):
    brand = owner(request, wid)
    from .research import CSV_COLUMNS

    with db.connect() as c:
        exp = get(c, wid, "experiment", eid)
        existing = db.rows(c, wid, "metric")
    if not exp["variant_id"]:
        raise HTTPException(409, "Prepare the variant first")
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for i, vid in enumerate([exp["baseline_id"], exp["variant_id"]]):
        prior = [r for r in existing if r["video_id"] == vid]
        if brand["synthetic"] and prior:
            row = prior[0]
        else:
            row = dict(
                publication_id=("synthetic-" if brand["synthetic"] else "replace-post-")
                + vid,
                video_id=vid,
                platform="instagram",
                traffic="organic",
                source=(
                    "synthetic-demo-v1"
                    if brand["synthetic"]
                    else "manual-platform-export"
                ),
                period_start="2026-10-01",
                period_end="2026-10-08",
                views=1000 if brand["synthetic"] else "",
                retention_3s=(0.40 if i == 0 else 0.49) if brand["synthetic"] else "",
                retention_unit="fraction",
            )
        writer.writerow(row)
    return Response(
        out.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="experiment-results.csv"'
        },
    )


def reserve(op, wid):
    budget = float(os.environ.get("CE_OPENAI_APPROVED_BUDGET_USD", "0"))
    if not math.isfinite(budget) or not 0 < budget <= 10:
        raise ValueError("Approved budget must be finite and between 0 and $10")
    with db.connect() as c:
        c.execute("BEGIN IMMEDIATE")
        history = [
            json.loads(r[0])
            for r in c.execute("SELECT payload FROM records WHERE kind='operation'")
        ]
        if any(x.get("budget_halted") for x in history):
            raise ValueError(
                "Previous API cost or outcome needs review. Live requests halted."
            )
        if sum(x.get("reservation_usd", 0) for x in history) + 0.10 > budget:
            raise ValueError("Shared API reservation budget exhausted")
        op["reservation_usd"] = 0.10
        op["budget_halted"] = True
        db.save(c, wid, "operation", op)


def reconcile(op):
    cost = op.get("cost_usd")
    op["budget_halted"] = cost is None or cost > 0.10
    if op["budget_halted"]:
        op["budget_note"] = (
            "Cost missing or exceeded reservation. Further API calls halted for budget review."
        )


@app.post("/api/workspaces/{wid}/recommendations/generate")
def generate_recommendations(request: Request, wid: str):
    owner(request, wid)
    if not os.environ.get("CE_OPENAI_APPROVED_BUDGET_USD"):
        raise HTTPException(
            403, "Live API is disabled pending model and spending approval"
        )
    from .research import recommend

    with db.connect() as c:
        candidates = recommend(db.rows(c, wid, "video"), db.rows(c, wid, "metric"))
    if not candidates:
        raise HTTPException(409, "Upload and analyze a video first")

    def work(op):
        from .provider import propose

        reserve(op, wid)
        result, audit = propose(candidates, authorized=True)
        op.update(audit)
        reconcile(op)
        with db.connect() as c:
            c.execute(
                "DELETE FROM records WHERE wid=? AND kind='recommendation'", (wid,)
            )
            for r in result:
                r["id"] = wid + "-" + r["id"]
                db.save(c, wid, "recommendation", r)
        return result

    return launch(wid, "recommendation", {"candidates": candidates}, work)
