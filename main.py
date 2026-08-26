from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
from contextlib import asynccontextmanager

from app.database import Base, engine
from app.routers import auth, products, stock_sales, ai_insights, documents, license as license_router
from app.services.license import require_active_license
from fastapi import Depends


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
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files & templates
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")
templates = Jinja2Templates(directory="frontend/templates")

# Routers
app.include_router(auth.router)
app.include_router(license_router.router)  # not license-gated  you must be able to check/renew even when expired
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
