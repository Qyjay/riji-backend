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

    # MiniMax AI（TokenPlan Plus）
    MINIMAX_API_KEY: str = ""
    MINIMAX_API_BASE: str = "https://api.minimaxi.com"
    MINIMAX_MODEL: str = "MiniMax-M2.7-highspeed"
    MINIMAX_MOCK: bool = True  # True=返回模拟数据不调真实API，False=调真实API

    # 文件上传
    UPLOAD_DIR: str = "./uploads"
    MAX_FILE_SIZE: int = 10485760  # 10MB

    # 服务器
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # OpenClaw Gateway（AI 对话带记忆）
    OPENCLAW_GATEWAY_URL: str = "http://127.0.0.1:18789"
    OPENCLAW_GATEWAY_TOKEN: str = ""
    OPENCLAW_AGENT_ID: str = "riji"
    OPENCLAW_ENABLED: bool = False

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


# 全局配置单例
settings = Settings()
