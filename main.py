from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.database import Base, engine
from app.config import get_settings
from app.limiter import limiter
from app.routers import auth, products, stock_sales, ai_insights, documents, license as license_router
from app.services.license import require_active_license
from fastapi import Depends

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create all tables on startup
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="SmartStock AI",
    description="AI-powered inventory intelligence for SME retailers",
    version="1.0.0",
    lifespan=lifespan,
    # Interactive API docs leak your whole schema and give attackers a map
    # of every endpoint — keep them on for local dev only, off in production
    # (set DEBUG=False) unless you deliberately want a public API reference.
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    openapi_url="/openapi.json" if settings.debug else None,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS: never combine allow_origins=["*"] with allow_credentials=True — the
# browser rejects that combination anyway, and the app uses an httpOnly
# auth cookie, so we need an explicit origin allow-list. Configure extra
# production origins via the CORS_ORIGINS env var (comma-separated).
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if not settings.debug:
        # Only advertise HSTS once you're actually serving over HTTPS
        # (true in production); it would break local http:// dev.
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return response


# Static files & templates
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")
templates = Jinja2Templates(directory="frontend/templates")

# Routers
app.include_router(auth.router)
app.include_router(license_router.router)  # not license-gated — you must be able to check/renew even when expired
app.include_router(products.router, dependencies=[Depends(require_active_license)])
app.include_router(stock_sales.router, dependencies=[Depends(require_active_license)])
app.include_router(ai_insights.router, dependencies=[Depends(require_active_license)])
app.include_router(documents.router, dependencies=[Depends(require_active_license)])


@app.get("/", include_in_schema=False)
async def dashboard(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/health")
def health():
    return {"status": "ok", "service": "SmartStock AI"}
