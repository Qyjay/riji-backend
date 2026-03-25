"""
日迹 App 后端配置
使用 pydantic-settings 从 .env 文件读取配置
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # 数据库
    DATABASE_URL: str = "sqlite:///./data.db"

    # JWT 认证
    JWT_SECRET: str = "dev-secret-key-please-change-in-production"
    JWT_EXPIRE_DAYS: int = 7

    # MiniMax AI
    MINIMAX_API_KEY: str = ""
    MINIMAX_API_BASE: str = "https://api.minimax.chat/v1"
    MINIMAX_MODEL: str = "MiniMax-M1"

    # 文件上传
    UPLOAD_DIR: str = "./uploads"
    MAX_FILE_SIZE: int = 10485760  # 10MB

    # 服务器
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


# 全局配置单例
settings = Settings()
