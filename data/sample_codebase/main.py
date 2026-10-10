"""Main entry point for the mock Pakistani Fintech Backend API."""

from fastapi import FastAPI
from data.sample_codebase.api.routes.disbursement import router as disbursement_router
from data.sample_codebase.api.routes.easypaisa_callback import router as easypaisa_router
from data.sample_codebase.api.routes.jazzcash_callback import router as jazzcash_router
from data.sample_codebase.api.routes.payment_status import router as payment_status_router
from data.sample_codebase.config.settings import app_settings

app = FastAPI(
    title=app_settings.app_name,
    description="Mock Pakistani Fintech payment switch and aggregator backend for CodeGraph RAG.",
    version="1.0.0",
)

# Register route controllers
app.include_router(jazzcash_router)
app.include_router(easypaisa_router)
app.include_router(payment_status_router)
app.include_router(disbursement_router)


@app.get("/health")
def health_check() -> dict[str, str]:
    """Service health and readiness check."""
    return {"status": "HEALTHY", "environment": app_settings.environment}
