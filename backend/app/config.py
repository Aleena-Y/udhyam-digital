from pydantic_settings import BaseSettings
from datetime import date


class Settings(BaseSettings):
    # App
    APP_NAME: str = "Udyam Digital API"
    DEBUG: bool = True
    SECRET_KEY: str = "udyam-digital-secret-key-change-in-prod"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    # Database
    DATABASE_URL: str = "sqlite:///./udyam_digital.db"

    # Demo business rules
    DEMO_REFERENCE_DATE: date = date(2026, 7, 15)
    ADDRESS_PROOF_MAX_DAYS: int = 90

    # Ollama AI
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "gemma4:31b-cloud"

    # Data paths (relative to backend/ directory)
    PRODUCT_CATALOGUE_PATH: str = "data/product_catalogue.csv"
    SMB_LEADS_PATH: str = "data/smb_leads.csv"
    GSTIN_REGISTRY_PATH: str = "data/mock_gstin_registry.csv"
    UDYAM_REGISTRY_PATH: str = "data/mock_udyam_registry.csv"
    KYC_DOCUMENTS_PATH: str = "data/kyc_documents"

    # Upload storage
    UPLOAD_DIR: str = "./uploads"

    # Partner commission policy (demo)
    DEFAULT_COMMISSION_RATE: float = 0.08  # 8% of monthly bundle value

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
