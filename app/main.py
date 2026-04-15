import logging
import traceback
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.core import init_redis, close_redis, connect_db, settings, init_firebase
from app.api import api_router
from app.core.bootstrap import bootstrap_admin

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


from app.api.ws.manager import manager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_redis()
    await connect_db()
    init_firebase()
    await bootstrap_admin()
    await manager.start_listening()
    yield
    # Shutdown
    await manager.stop_listening()
    await close_redis()


app = FastAPI(
    title="Safe City API",
    description="API for Safe City emergency response system",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure properly in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(api_router)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global exception caught: {exc}")
    logger.error(traceback.format_exc())
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "message": "Internal Server Error",
            "detail": str(exc) if settings.debug else "An unexpected error occurred"
        }
    )


@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "1.0.0"}


@app.get("/")
async def root():
    return {
        "name": "Safe City API",
        "version": "1.0.0",
        "docs": "/docs"
    }
