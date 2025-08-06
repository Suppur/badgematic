import os
from fastapi import FastAPI, Request, Form, Response, status, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from itsdangerous import URLSafeSerializer, BadSignature

# Config
SECRET_KEY = os.getenv("BADGEMATIC_SECRET_KEY", "dev_secret_badgematic")
SESSION_COOKIE = "badgematic_session"

# App and templates
app = FastAPI()
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

# Session serializer
serializer = URLSafeSerializer(SECRET_KEY, salt="badgematic")

# Helper: get current session data
def get_session_data(request: Request):
    cookie = request.cookies.get(SESSION_COOKIE)
    if not cookie:
        return {}
    try:
        return serializer.loads(cookie)
    except BadSignature:
        return {}

# Helper: set session data
def set_session_data(response: Response, data: dict):
    response.set_cookie(
        SESSION_COOKIE, serializer.dumps(data),
        httponly=True, max_age=3600, samesite="lax"
    )

# Routes

@app.get("/", response_class=HTMLResponse)
async def welcome(request: Request):
    return templates.TemplateResponse("welcome.html", {"request": request})

@app.get("/form", response_class=HTMLResponse)
async def form_get(request: Request):
    session = get_session_data(request)
    return templates.TemplateResponse("form.html", {"request": request, "formdata": session.get("formdata", {})})

@app.post("/form", response_class=HTMLResponse)
async def form_post(
    request: Request,
    name: str = Form(...),
    employee_number: str = Form(...),
    title: str = Form(...),
    phone: str = Form(...),
    email: str = Form(...)
):
    formdata = {
        "name": name, "employee_number": employee_number,
        "title": title, "phone": phone, "email": email
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
        return RedirectResponse("/form")
    return templates.TemplateResponse("photo.html", {"request": request, "formdata": session["formdata"]})

@app.post("/photo", response_class=HTMLResponse)
async def photo_post(
    request: Request,
    photo_data: str = Form(...)
):
    session = get_session_data(request)
    if "formdata" not in session:
        return RedirectResponse("/form")
    session["photo_data"] = photo_data
    response = RedirectResponse("/review", status_code=status.HTTP_303_SEE_OTHER)
    set_session_data(response, session)
    return response

@app.get("/review", response_class=HTMLResponse)
async def review_get(request: Request):
    session = get_session_data(request)
    if "formdata" not in session or "photo_data" not in session:
        return RedirectResponse("/form")
    return templates.TemplateResponse("review.html", {
        "request": request,
        "formdata": session["formdata"],
        "photo_data": session["photo_data"],
        # TODO: card preview
    })

@app.post("/review/edit", response_class=HTMLResponse)
async def review_edit(
    request: Request,
    name: str = Form(...),
    employee_number: str = Form(...),
    title: str = Form(...),
    phone: str = Form(...),
    email: str = Form(...)
):
    session = get_session_data(request)
    session["formdata"] = {
        "name": name, "employee_number": employee_number,
        "title": title, "phone": phone, "email": email
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

@app.post("/print")
async def print_card(request: Request):
    session = get_session_data(request)
    if "formdata" not in session or "photo_data" not in session:
        return RedirectResponse("/form")
    # TODO: template + print logic
    session["print_status"] = "processing"
    # TODO: Save badge PNG path/ID if needed
    response = RedirectResponse("/confirm", status_code=status.HTTP_303_SEE_OTHER)
    set_session_data(response, session)
    return response

@app.get("/confirm", response_class=HTMLResponse)
async def confirm_get(request: Request):
    session = get_session_data(request)
    print_status = session.get("print_status", "processing")
    return templates.TemplateResponse("confirm.html", {
        "request": request,
        "print_status": print_status
    })

@app.post("/feedback")
async def feedback_post(
    request: Request,
    rating: int = Form(...),
    comments: str = Form(None)
):
    # TODO add DB / sharepoint
    print(f"Received feedback: {rating} stars, comments: {comments}")
    response = RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(SESSION_COOKIE) 
    return response

@app.post("/reset")
async def reset_process(request: Request):
    response = RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(SESSION_COOKIE)
    return response

