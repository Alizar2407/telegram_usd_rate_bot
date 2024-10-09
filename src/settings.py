from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    BOT_API_TOKEN: str
    REDIS_URL: str = "redis://localhost"

    class Config:
        env_file = ".env"


settings = Settings()
