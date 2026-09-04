"""Main FastAPI application entry point."""

import os
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import logger, settings
from app.models.course import Course
from app.routers import admin, auth, courses, documents, generation, jobs, upload
from app.services.admin_seed import seed_default_admin
from app.services.database import SessionLocal
from app.services.inline_job_recovery import reconcile_interrupted_inline_preprocess_jobs
from app.services.vector_store import get_vector_store

START_TIME = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    seed_default_admin()
    reconcile_interrupted_inline_preprocess_jobs()
    yield


app = FastAPI(
    title="HackaGen API",
    version="3.0.0",
    description="HackaGen API - Core Infrastructure & Auth",
    lifespan=lifespan,
)

# Configure CORS (CRITICAL)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,  # MUST BE TRUE for cookies
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(auth.router)
app.include_router(courses.router)
app.include_router(courses.router_single)
app.include_router(upload.router)
app.include_router(documents.router)
app.include_router(jobs.router)
app.include_router(generation.router)
app.include_router(generation.router_single)
app.include_router(generation.router_generate)
app.include_router(generation.router_docs)
app.include_router(admin.router)


@app.exception_handler(HTTPException)
async def http_exception_handler(
    request: Request, exc: HTTPException
) -> JSONResponse:
    """Global exception handler for HTTPException with consistent format."""
    logger.warning(
        "HTTPException on %s %s - Status: %s - Detail: %s",
        request.method,
        request.url.path,
        exc.status_code,
        exc.detail,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=exc.headers,
    )


@app.exception_handler(Exception)
async def general_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Global exception handler for unexpected errors without exposing stack traces."""
    logger.error(
        "Unhandled exception on %s %s: %s",
        request.method,
        request.url.path,
        exc,
        exc_info=True,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Đã xảy ra lỗi hệ thống. Vui lòng thử lại sau."},
    )



@app.get("/", tags=["root"])
def root():
    """Health check endpoint."""
    return {"status": "ok", "service": "HackaGen API v3.0.0"}


@app.get("/health", tags=["health"])
def health_check():
    """Readiness endpoint for frontend proxy."""
    try:
        vs = get_vector_store()
        vector_db_ready = vs is not None and hasattr(vs, "collection") and vs.collection is not None
        error_msg = None
    except Exception as e:
        vector_db_ready = False
        error_msg = str(e)

    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    os.makedirs(settings.OUTPUT_DIR, exist_ok=True)
    upload_dir_ok = os.path.exists(settings.UPLOAD_DIR)
    output_dir_ok = os.path.exists(settings.OUTPUT_DIR)
    ready = vector_db_ready and upload_dir_ok and output_dir_ok

    return {
        "status": "ok" if ready else "error",
        "ready": ready,
        "details": {
            "upload_dir": upload_dir_ok,
            "output_dir": output_dir_ok,
            "vector_db": vector_db_ready,
            "config_loaded": True,
        },
        "vector_db_provider": getattr(settings, "VECTOR_DB_PROVIDER", "chroma"),
        "vector_db_ready": vector_db_ready,
        "chroma_persist_dir": settings.CHROMA_PERSIST_DIR,
        "chroma_collection_name": settings.CHROMA_COLLECTION_NAME,
        "startup_duration_seconds": round(time.time() - START_TIME, 2),
        "error": error_msg,
    }


@app.get("/api/health", tags=["health"])
def api_health_check():
    """Returns backend status and list of course_ids."""
    db = SessionLocal()
    try:
        courses = db.query(Course.id).all()
        course_ids = [c[0] for c in courses]
    except Exception as e:
        logger.warning(f"Error querying courses for health check: {e}")
        course_ids = []
    finally:
        db.close()

    return {
        "status": "ok",
        "service": "HackaGen API v3.0.0",
        "courses": course_ids,
        "course_ids": course_ids,
    }
