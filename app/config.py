import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def load_dotenv() -> None:
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


load_dotenv()

APP_NAME = os.getenv("APP_NAME", "Creator OS")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
RELOAD = os.getenv("RELOAD", "true").lower() in ("1", "true", "yes")
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me")
DATABASE_URL = os.getenv("DATABASE_URL") or f"sqlite:///{BASE_DIR / 'creator_os.db'}"
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() in ("1", "true", "yes")
PBKDF2_ITERATIONS = int(os.getenv("PBKDF2_ITERATIONS", "260000"))
SESSION_TTL_DAYS = int(os.getenv("SESSION_TTL_DAYS", "30"))
