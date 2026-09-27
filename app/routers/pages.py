from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from app.config import settings
from app.auth import get_current_user_optional

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=str(settings.BASE_DIR / "app" / "templates"))


@router.get("/", response_class=HTMLResponse)
def page_home(request: Request):
    user = get_current_user_optional(request)
    return templates.TemplateResponse("public/home.html", {"request": request, "user": user})


@router.get("/pricing", response_class=HTMLResponse)
def page_pricing(request: Request):
    user = get_current_user_optional(request)
    return templates.TemplateResponse("public/pricing.html", {"request": request, "user": user})


@router.get("/customers", response_class=HTMLResponse)
def page_customers(request: Request):
    user = get_current_user_optional(request)
    return templates.TemplateResponse("public/customers.html", {"request": request, "user": user})


@router.get("/customers/northwind-analytics", response_class=HTMLResponse)
def page_case_study(request: Request):
    user = get_current_user_optional(request)
    return templates.TemplateResponse("public/case_study.html", {"request": request, "user": user})


@router.get("/docs", response_class=HTMLResponse)
def page_docs(request: Request):
    user = get_current_user_optional(request)
    return templates.TemplateResponse("public/docs.html", {"request": request, "user": user})


@router.get("/changelog", response_class=HTMLResponse)
def page_changelog(request: Request):
    user = get_current_user_optional(request)
    return templates.TemplateResponse("public/changelog.html", {"request": request, "user": user})


@router.get("/about", response_class=HTMLResponse)
def page_about(request: Request):
    user = get_current_user_optional(request)
    return templates.TemplateResponse("public/about.html", {"request": request, "user": user})


@router.get("/contact", response_class=HTMLResponse)
def page_contact(request: Request):
    user = get_current_user_optional(request)
    return templates.TemplateResponse("public/contact.html", {"request": request, "user": user})


@router.get("/status", response_class=HTMLResponse)
def page_status(request: Request):
    user = get_current_user_optional(request)
    return templates.TemplateResponse("public/status.html", {"request": request, "user": user})


@router.get("/security", response_class=HTMLResponse)
def page_security(request: Request):
    user = get_current_user_optional(request)
    return templates.TemplateResponse("public/security.html", {"request": request, "user": user})


@router.get("/terms", response_class=HTMLResponse)
def page_terms(request: Request):
    user = get_current_user_optional(request)
    return templates.TemplateResponse("public/terms.html", {"request": request, "user": user})


@router.get("/privacy", response_class=HTMLResponse)
def page_privacy(request: Request):
    user = get_current_user_optional(request)
    return templates.TemplateResponse("public/privacy.html", {"request": request, "user": user})


@router.get("/login", response_class=HTMLResponse)
def page_login(request: Request):
    user = get_current_user_optional(request)
    if user:
        if user.get("role") == "operator":
            return RedirectResponse(url="/admin", status_code=302)
        return RedirectResponse(url="/app", status_code=302)
    return templates.TemplateResponse("public/login.html", {"request": request})


@router.get("/signup", response_class=HTMLResponse)
def page_signup(request: Request):
    user = get_current_user_optional(request)
    if user:
        return RedirectResponse(url="/app", status_code=302)
    return templates.TemplateResponse("public/signup.html", {"request": request})


@router.get("/forgot", response_class=HTMLResponse)
def page_forgot(request: Request):
    return templates.TemplateResponse("public/forgot.html", {"request": request})
