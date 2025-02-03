from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    ANTHROPIC_API_KEY: str
    OPENAI_API_KEY: str
    TAVILY_API_KEY: str
    DATABASE_URL: str = "sqlite:///./travel.db"
    
    class Config:
        env_file = ".env" 