from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    groq_api_key: str = ""
    # gemma2-9b-it (the model named in the assignment brief) has been decommissioned
    # by Groq — see docs/ARCHITECTURE.md §6. llama-3.1-8b-instant fills the same
    # role: fast/cheap, used for the high-frequency per-turn extraction pass.
    groq_extraction_model: str = "llama-3.1-8b-instant"
    groq_reasoning_model: str = "llama-3.3-70b-versatile"
    database_url: str = "postgresql+psycopg2://hcp_crm:hcp_crm@localhost:5432/hcp_crm"
    env: str = "development"
    cors_origins: str = "http://localhost:5173"

    class Config:
        env_file = ".env"


settings = Settings()
