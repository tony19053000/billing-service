import os
from pathlib import Path


class Settings:
    PORT: int = int(os.getenv("PORT", "8000"))
    HOST: str = os.getenv("HOST", "0.0.0.0")
    DATABASE_PATH: str = os.getenv("DATABASE_PATH", "./data/tallyo.db")
    ADMIN_EMAIL: str = os.getenv("ADMIN_EMAIL", "ops@tallyo.io")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "tallyo-admin")
    SEED_DATA: bool = os.getenv("SEED_DATA", "true").lower() in ("true", "1", "yes")
    BASE_DIR: Path = Path(__file__).resolve().parent.parent

    @property
    def db_file_path(self) -> Path:
        p = Path(self.DATABASE_PATH)
        if not p.is_absolute():
            return self.BASE_DIR / p
        return p


settings = Settings()
