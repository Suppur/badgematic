# app/main.py
import os
import uuid
import asyncio
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
    response = RedirectResponse("/photo", status_code=status.HTTP_303_SEE_OTHER)
    set_session_data(response, session)
    return response


@app.get("/photo", response_class=HTMLResponse)
async def photo_get(request: Request):
    session = get_session_data(request)
    if "formdata" not in session:
        return RedirectResponse("/form", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        "photo.html", {"request": request, "formdata": session["formdata"]}
    )


@app.post("/photo", response_class=HTMLResponse)
async def photo_post(request: Request, photo_data: str = Form(...)):
    session = get_session_data(request)
    if "formdata" not in session:
        return RedirectResponse("/form", status_code=status.HTTP_303_SEE_OTHER)
    session["photo_data"] = photo_data
    response = RedirectResponse("/review", status_code=status.HTTP_303_SEE_OTHER)
    set_session_data(response, session)
    return response


@app.get("/review", response_class=HTMLResponse)
async def review_get(request: Request):
    session = get_session_data(request)
    if "formdata" not in session or "photo_data" not in session:
        return RedirectResponse("/form", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        "review.html",
        {
            "request": request,
            "formdata": session["formdata"],
            "photo_data": session["photo_data"],
            # Optionally pass a generated preview path if you pre-render it
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
    session.pop("photo_data", None)
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
    if "formdata" not in session or "photo_data" not in session:
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
        simulate_print_pipeline, job_id, session["formdata"], session["photo_data"]
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
async def simulate_print_pipeline(job_id: str, formdata: dict, photo_data: str):
    # Step 1: image processing
    PRINT_JOBS[job_id]["step"] = "image_processing"
    await asyncio.sleep(0.3)  # simulate latency

    try:
        # Step 2: compose badge
        PRINT_JOBS[job_id]["step"] = "composing_badge"
        badge_path = generate_badge_png(formdata, photo_data)
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

    uvicorn.run(
        "app.main:app", host="127.0.0.1", port=8000, reload=True
    )
