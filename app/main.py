# app/main.py
import os
import uuid
import asyncio
import base64
from pathlib import Path
from typing import Dict

from fastapi import FastAPI, Request, Form, Response, status, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates
from itsdangerous import URLSafeSerializer, BadSignature

from app.utils import generate_badge_png

# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------
SECRET_KEY = os.getenv("BADGEMATIC_SECRET_KEY", "dev_secret_badgematic")
SESSION_COOKIE = "badgematic_session"
SESSION_MAX_AGE = 60 * 60  # 1 hour

# Paths (robust relative to this file)
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
UPLOAD_DIR = STATIC_DIR / "uploads"   # where we save captured photos
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# -----------------------------------------------------------------------------
# App & templating
# -----------------------------------------------------------------------------
app = FastAPI()

# Mount static for Tailwind/DaisyUI output, JS, images, etc.
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Jinja2 templates (path-safe)
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Print jobs in-memory registry
PRINT_JOBS: Dict[str, Dict] = {}  # job_id -> {"step": str, "status": str, "badge_path": str|None, "error": str|None}

# Signed-cookie session serializer
serializer = URLSafeSerializer(SECRET_KEY, salt="badgematic")


# -----------------------------------------------------------------------------
# Session helpers
# -----------------------------------------------------------------------------
def get_session_data(request: Request) -> dict:
    cookie = request.cookies.get(SESSION_COOKIE)
    if not cookie:
        return {}
    try:
        return serializer.loads(cookie)
    except BadSignature:
        # Bad/expired cookie -> treat as new session
        return {}


def set_session_data(response: Response, data: dict) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=serializer.dumps(data),
        httponly=True,
        max_age=SESSION_MAX_AGE,
        samesite="lax",
    )


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def save_data_url_to_file(data_url: str, dest_dir: Path) -> Path:
    """
    Accepts a data URL like 'data:image/jpeg;base64,...', saves it to dest_dir,
    returns the saved Path.
    """
    header, b64 = data_url.split(",", 1)
    # crude content-type sniff
    ext = ".jpg"
    if "image/png" in header:
        ext = ".png"
    filename = f"{uuid.uuid4().hex}{ext}"
    out_path = dest_dir / filename
    out_path.write_bytes(base64.b64decode(b64))
    return out_path


def file_to_data_url(path: Path) -> str:
    """
    Loads a file and returns a data URL (defaults to image/jpeg unless .png).
    """
    mime = "image/jpeg"
    if path.suffix.lower() == ".png":
        mime = "image/png"
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------
@app.get("/health")
async def health():
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
async def welcome(request: Request):
    return templates.TemplateResponse("welcome.html", {"request": request})


@app.get("/form", response_class=HTMLResponse)
async def form_get(request: Request):
    session = get_session_data(request)
    return templates.TemplateResponse(
        "form.html",
        {"request": request, "formdata": session.get("formdata", {})},
    )


@app.post("/form", response_class=HTMLResponse)
async def form_post(
    request: Request,
    name: str = Form(...),
    employee_number: str = Form(...),
    title: str = Form(...),
    phone: str = Form(...),
    email: str = Form(...),
):
    formdata = {
        "name": name,
        "employee_number": employee_number,
        "title": title,
        "phone": phone,
        "email": email,
    }
    session = get_session_data(request)
    session["formdata"] = formdata
    # clear any previous photo if user is restarting
    session.pop("photo_path", None)
    response = RedirectResponse("/photo", status_code=status.HTTP_303_SEE_OTHER)
    set_session_data(response, session)
    return response


@app.get("/photo", response_class=HTMLResponse)
async def photo_get(request: Request):
    session = get_session_data(request)
    if "formdata" not in session:
        return RedirectResponse("/form", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        "photo.html",
        {
            "request": request,
            "formdata": session["formdata"],
            "photo_path": session.get("photo_path"),  # allow showing last shot
        },
    )


@app.post("/photo", response_class=HTMLResponse)
async def photo_post(request: Request, photo_data: str = Form(...)):
    """
    Save the captured photo to disk; store only a small path in the cookie.
    """
    session = get_session_data(request)
    if "formdata" not in session:
        return RedirectResponse("/form", status_code=status.HTTP_303_SEE_OTHER)

    # Save large base64 image to a file to avoid cookie bloat
    saved_path = save_data_url_to_file(photo_data, UPLOAD_DIR)
    # Store a short static path usable by templates: "/static/uploads/<file>"
    session["photo_path"] = f"/static/uploads/{saved_path.name}"

    response = RedirectResponse("/review", status_code=status.HTTP_303_SEE_OTHER)
    set_session_data(response, session)
    return response


@app.get("/review", response_class=HTMLResponse)
async def review_get(request: Request):
    session = get_session_data(request)
    if "formdata" not in session or "photo_path" not in session:
        return RedirectResponse("/form", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        "review.html",
        {
            "request": request,
            "formdata": session["formdata"],
            "photo_path": session["photo_path"],  # used for preview <img src=...>
        },
    )


@app.post("/review/edit", response_class=HTMLResponse)
async def review_edit(
    request: Request,
    name: str = Form(...),
    employee_number: str = Form(...),
    title: str = Form(...),
    phone: str = Form(...),
    email: str = Form(...),
):
    session = get_session_data(request)
    session["formdata"] = {
        "name": name,
        "employee_number": employee_number,
        "title": title,
        "phone": phone,
        "email": email,
    }
    response = RedirectResponse("/review", status_code=status.HTTP_303_SEE_OTHER)
    set_session_data(response, session)
    return response


@app.post("/review/retake_photo")
async def retake_photo(request: Request):
    session = get_session_data(request)
    # Optional: delete previous file to keep storage tidy
    old = session.pop("photo_path", None)
    if old:
        try:
            (UPLOAD_DIR / Path(old).name).unlink(missing_ok=True)
        except Exception:
            pass
    response = RedirectResponse("/photo", status_code=status.HTTP_303_SEE_OTHER)
    set_session_data(response, session)
    return response


# --- HTMX status fragment for polling ---
@app.get("/status", response_class=HTMLResponse)
async def status_partial(request: Request):
    session = get_session_data(request)
    job_id = session.get("job_id")
    job = PRINT_JOBS.get(job_id or "", {"status": "idle", "step": "idle"})
    return templates.TemplateResponse(
        "partials/_status_block.html",
        {"request": request, "job": job},
    )


@app.post("/print")
async def print_card(request: Request, background: BackgroundTasks):
    session = get_session_data(request)
    if "formdata" not in session or "photo_path" not in session:
        return RedirectResponse("/form", status_code=status.HTTP_303_SEE_OTHER)

    # Create job & persist id in session
    job_id = str(uuid.uuid4())
    PRINT_JOBS[job_id] = {
        "status": "processing",
        "step": "queued",
        "badge_path": None,
        "error": None,
    }
    session["job_id"] = job_id

    # Redirect immediately to confirm page
    response = RedirectResponse("/confirm", status_code=status.HTTP_303_SEE_OTHER)
    set_session_data(response, session)

    # Kick off background pipeline
    background.add_task(
        simulate_print_pipeline, job_id, session["formdata"], session["photo_path"]
    )
    return response


@app.get("/confirm", response_class=HTMLResponse)
async def confirm_get(request: Request):
    # The page hosts the HTMX polling block that hits /status
    return templates.TemplateResponse("confirm.html", {"request": request})


@app.post("/feedback")
async def feedback_post(
    request: Request, rating: int = Form(...), comments: str = Form(None)
):
    # TODO: Persist to DB or file as needed
    print(f"Received feedback: {rating} stars, comments: {comments}")
    response = RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(SESSION_COOKIE)
    return response


@app.post("/reset")
async def reset_process(request: Request):
    response = RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(SESSION_COOKIE)
    return response


# -----------------------------------------------------------------------------
# Background pipeline (simulate compose + print)
# -----------------------------------------------------------------------------
async def simulate_print_pipeline(job_id: str, formdata: dict, photo_path_str: str):
    # Step 1: image processing
    PRINT_JOBS[job_id]["step"] = "image_processing"
    await asyncio.sleep(0.3)  # simulate latency

    try:
        # Step 2: compose badge
        PRINT_JOBS[job_id]["step"] = "composing_badge"

        # utils.generate_badge_png expects a base64 data URL,
        # so convert the saved file to data URL here:
        disk_path = (UPLOAD_DIR / Path(photo_path_str).name)
        photo_data_url = file_to_data_url(disk_path)

        badge_path = generate_badge_png(formdata, photo_data_url)
        PRINT_JOBS[job_id]["badge_path"] = badge_path
        await asyncio.sleep(0.3)

        # Step 3: send to printer (stub)
        PRINT_JOBS[job_id]["step"] = "printing"
        # Example (Windows): quick print via Paint
        # import subprocess
        # subprocess.run(['mspaint.exe', '/p', badge_path], check=False)
        await asyncio.sleep(0.8)

        PRINT_JOBS[job_id]["status"] = "success"
        PRINT_JOBS[job_id]["step"] = "done"
    except Exception as e:
        PRINT_JOBS[job_id]["status"] = "error"
        PRINT_JOBS[job_id]["error"] = str(e)
        PRINT_JOBS[job_id]["step"] = "failed"


# -----------------------------------------------------------------------------
# Local dev entry (optional)
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
