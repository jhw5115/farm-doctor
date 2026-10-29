from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from sqlalchemy import text
from app.config import settings
from app.database import engine
from app.inspections import router as inspections_router
from app.ml import classifier
from app.statistics import router as statistics_router
from app.reports import router as reports_router
from app.chat import router as chat_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    classifier.load()
    yield
    engine.dispose()


app = FastAPI(title="사과 과수화상병 AI 판별 API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
app.include_router(inspections_router)
app.include_router(statistics_router)
app.include_router(reports_router)
app.include_router(chat_router)


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/docs")


@app.get("/api/v1/health", tags=["health"])
def health() -> dict:
    database_ready = True
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        database_ready = False
    return {"status": "ready" if database_ready else "degraded", "database_ready": database_ready, "model_ready": classifier.status.ready, "model_detail": classifier.status.detail}
