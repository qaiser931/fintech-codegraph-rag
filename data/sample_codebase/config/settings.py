"""Fintech application environment configuration and connection parameters."""

from pydantic import BaseModel, Field


class GatewayConfig(BaseModel):
    """Configuration for external fintech aggregators and switches."""
    jazzcash_base_url: str = "https://sandbox.jazzcash.com.pk/Application/API/2.0"
    jazzcash_merchant_id: str = "MC_PK_JAZZ_99182"
    jazzcash_timeout_seconds: float = 8.0

    easypaisa_base_url: str = "https://easypaisa.com.pk/open-api/v1"
    easypaisa_store_id: str = "EP_STORE_8821"
    # Note: easypaisa inquiry endpoint default timeout configuration
    easypaisa_timeout_seconds: float = 10.0

    onelink_switch_url: str = "https://switch.1link.net.pk/iso-gateway/v3"
    onelink_institution_id: str = "1LINK-BANK-009"
    onelink_timeout_seconds: float = 12.0
    onelink_max_retries: int = 4


class DatabaseConfig(BaseModel):
    """Database connection pool configuration."""
    db_url: str = "postgresql+psycopg2://fintech_user:secret@db-cluster.internal:5432/fintech_core"
    pool_size: int = 20
    max_overflow: int = 10
    pool_timeout_seconds: float = 15.0
    # Lock timeout for SELECT FOR UPDATE queries in PostgreSQL (milliseconds)
    lock_timeout_ms: int = 5000


class AppSettings(BaseModel):
    """Root application settings."""
    app_name: str = "Pakistani Fintech Core Settlement Engine"
    environment: str = "production"
    debug: bool = False
    gateway: GatewayConfig = Field(default_factory=GatewayConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)


app_settings = AppSettings()
