import logging
from pydantic_settings import BaseSettings


# 第一部分 - 配置和模型
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    PROJECT_NAME: str = "Travel Assistant Support Bot"
    API_V1_STR: str = "/api/v1"
    ANTHROPIC_API_KEY: str
    OPENAI_API_KEY: str 
    TAVILY_API_KEY: str
    DATABASE_URL: str = "sqlite:///database/travel2.sqlite"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # 记录配置加载情况
        logger.debug(f"加载项目名称: {self.PROJECT_NAME}")
        logger.debug(f"API版本: {self.API_V1_STR}")
        logger.debug(f"数据库URL: {self.DATABASE_URL}")
        # 敏感信息只记录是否存在
        logger.debug(f"Anthropic API Key 已设置: {bool(self.ANTHROPIC_API_KEY)}")
        logger.debug(f"OpenAI API Key 已设置: {bool(self.OPENAI_API_KEY)}")
        logger.debug(f"Tavily API Key 已设置: {bool(self.TAVILY_API_KEY)}")

    class Config:
        env_file = ".env"

settings = Settings()
