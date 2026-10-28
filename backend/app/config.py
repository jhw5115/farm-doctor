import os
from pathlib import Path


class Settings:
    app_env = os.getenv("APP_ENV", "development")
    log_level = os.getenv("LOG_LEVEL", "info")
    database_url = os.getenv("DATABASE_URL", "mysql+pymysql://farm_doctor:local-development-only@localhost:3306/farm_doctor?charset=utf8mb4")
    cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
    storage_backend = os.getenv("STORAGE_BACKEND", "local").lower()
    local_storage_path = Path(os.getenv("LOCAL_STORAGE_PATH", "./uploads"))
    s3_bucket = os.getenv("S3_BUCKET", "")
    model_path = Path(os.getenv("MODEL_PATH", "./models/best.pt"))
    model_version = os.getenv("MODEL_VERSION", "apple_binary_v1")
    max_upload_size = int(os.getenv("MAX_UPLOAD_SIZE_MB", "10")) * 1024 * 1024
    max_upload_files = int(os.getenv("MAX_UPLOAD_FILES", "10"))
    openai_api_key = os.getenv("OPENAI_API_KEY", "")
    chat_model = os.getenv("CHAT_MODEL", "")
    chat_requests_per_minute = int(os.getenv("CHAT_REQUESTS_PER_MINUTE", "10"))
    chat_max_input_chars = int(os.getenv("CHAT_MAX_INPUT_CHARS", "1000"))
    chat_timeout_seconds = int(os.getenv("CHAT_TIMEOUT_SECONDS", "30"))
    chat_retention_days = int(os.getenv("CHAT_RETENTION_DAYS", "30"))
    openai_vector_store_id = os.getenv("OPENAI_VECTOR_STORE_ID", "")


settings = Settings()
