from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.db import init_db
from app.seed import seed_database
from fastapi.templating import Jinja2Templates
from app.routers import (
    auth,
    plans,
    subscription,
    credits,
    usage,
    invoices,
    clock,
    admin,
    pages,
)

templates = Jinja2Templates(directory=str(settings.BASE_DIR / "app" / "templates"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize database and seed if required
    init_db()
    if settings.SEED_DATA:
        seed_database()
    yield


app = FastAPI(
    title="Tallyo Billing Service",
    description="Production-grade SaaS subscription metering, billing, and customer portal platform.",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)


@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
    accept_header = request.headers.get("accept", "")
    is_html = "text/html" in accept_header and not request.url.path.startswith("/api/")
    if is_html:
        if exc.status_code == 404:
            return templates.TemplateResponse("404.html", {"request": request}, status_code=404)
        if exc.status_code >= 500:
            return templates.TemplateResponse("500.html", {"request": request}, status_code=500)

    if isinstance(exc.detail, dict) and "error" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": "http_error", "message": str(exc.detail)}},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    first_msg = errors[0]["msg"] if errors else "Validation failed"
    first_field = ".".join(str(x) for x in errors[0]["loc"]) if errors else "request"
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error": {"code": "validation_error", "message": f"{first_field}: {first_msg}"}},
    )


# Health check at root /health
@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "ok"}


# Mount static assets directory
static_dir = settings.BASE_DIR / "app" / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Mount API routers under /api/v1
api_prefix = "/api/v1"
app.include_router(auth.router, prefix=api_prefix)
app.include_router(plans.router, prefix=api_prefix)
app.include_router(subscription.router, prefix=api_prefix)
app.include_router(credits.router, prefix=api_prefix)
app.include_router(usage.router, prefix=api_prefix)
app.include_router(invoices.router, prefix=api_prefix)
app.include_router(clock.router, prefix=api_prefix)
app.include_router(admin.router, prefix=api_prefix)

# Mount public & portal page router
app.include_router(pages.router)

