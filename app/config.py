"""
日迹 App 后端配置
使用 pydantic-settings 从 .env 文件读取配置
"""
from pathlib import Path

from pydantic_settings import BaseSettings


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _resolve_sqlite_url(database_url: str) -> str:
    """将 sqlite 相对路径统一解析为后端目录下的绝对路径。"""
    raw = str(database_url or "").strip()
    if not raw.startswith("sqlite:///"):
        return raw

    path_part = raw[len("sqlite:///"):]
    if not path_part:
        return raw

    # sqlite:////abs/path 这类绝对路径保持原样
    if path_part.startswith("/"):
        return raw

    resolved = (PROJECT_ROOT / Path(path_part)).resolve()
    return f"sqlite:///{resolved.as_posix()}"


def _resolve_upload_dir(upload_dir: str) -> str:
    """将上传目录解析为后端目录下的绝对路径。"""
    raw = str(upload_dir or "").strip()
    if not raw:
        return str((PROJECT_ROOT / "uploads").resolve())

    path = Path(raw)
    if path.is_absolute():
        return str(path)
    return str((PROJECT_ROOT / path).resolve())


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

    # 视觉理解模型（火山引擎 Ark）
    ARK_API_KEY: str = ""
    ARK_BASE_URL: str = "https://ark.cn-beijing.volces.com/api/v3"
    ARK_VISION_MODEL: str = "doubao-seed-2-0-mini-260215"
    ARK_VISION_ENABLED: bool = True
    ARK_VISION_PROMPT: str = "请识别并描述这张图片的可见内容，输出一段中文详实介绍。要求包含：主体对象、场景环境、人物动作或状态、关键细节、整体氛围；表述客观连贯，约80-150字，不要编造图片中看不见的信息。"
    ARK_VISION_MAX_IMAGES: int = 10
    ARK_VISION_TIMEOUT_SEC: int = 50
    ARK_VISION_CACHE_TTL_SEC: int = 21600

    # 文件上传
    UPLOAD_DIR: str = "./uploads"
    MAX_FILE_SIZE: int = 10485760  # 10MB

    # 服务器
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    model_config = {
        "env_file": str(PROJECT_ROOT / ".env"),
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


# 全局配置单例
settings = Settings()
settings.DATABASE_URL = _resolve_sqlite_url(settings.DATABASE_URL)
settings.UPLOAD_DIR = _resolve_upload_dir(settings.UPLOAD_DIR)
