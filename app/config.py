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
    LLM_PROVIDER: str = "vivo"  # minimax | vivo | ark
    MINIMAX_API_KEY: str = ""
    MINIMAX_API_BASE: str = "https://api.minimaxi.com"
    MINIMAX_MODEL: str = "MiniMax-M2.7-highspeed"
    MINIMAX_MOCK: bool = False  # True=返回模拟数据不调真实API，False=调真实API

    # VIVO 大模型（OpenAI 兼容 chat/completions）
    VIVO_APP_ID: str = ""
    VIVO_APP_KEY: str = ""
    VIVO_API_BASE: str = "https://api-ai.vivo.com.cn"
    VIVO_MODEL: str = "Doubao-Seed-2.0-mini"
    VIVO_REASONING_EFFORT: str = "minimal"  # minimal | low | medium | high
    VIVO_ENABLE_THINKING: bool = False
    VIVO_TIMEOUT_SEC: int = 60
    VIVO_IMAGE_MODEL: str = "Doubao-Seedream-4.5"
    VIVO_IMAGE_TIMEOUT_SEC: int = 90
    VIVO_TTS_ENGINE_ID: str = "short_audio_synthesis_jovi"
    VIVO_TTS_TIMEOUT_SEC: int = 60
    VIVO_ASR_ENGINE_ID: str = "shortasrinput"
    VIVO_ASR_TIMEOUT_SEC: int = 70
    VIVO_ASR_END_VAD_TIME: int = 2000
    VIVO_ASR_PUNCTUATION: int = 1
    VIVO_ASR_CHINESE2DIGITAL: int = 1
    VIVO_ASR_NET_TYPE: int = 1
    VIVO_EMBEDDING_BASE_URL: str = "https://api-ai.vivo.com.cn"
    VIVO_EMBEDDING_MODEL: str = "m3e-base"
    VIVO_EMBEDDING_QUERY_INSTRUCTION: str = "为这个句子生成表示以用于检索相关文章："
    VIVO_VISION_ENABLED: bool = True
    VIVO_VISION_MODEL: str = "Doubao-Seed-2.0-mini"
    VIVO_VISION_PROMPT: str = "请识别并描述这张图片的可见内容，输出一段中文详实介绍。要求包含：主体对象、场景环境、人物动作或状态、关键细节、整体氛围；表述客观连贯，约80-150字，不要编造图片中看不见的信息。"
    VIVO_VISION_MAX_IMAGES: int = 10
    VIVO_VISION_TIMEOUT_SEC: int = 50
    VIVO_VISION_CACHE_TTL_SEC: int = 21600

    # 联网搜索
    WEB_SEARCH_PROVIDER: str = "exa"  # exa | volcengine

    # Exa 联网搜索
    EXA_API_KEY: str = ""
    EXA_API_BASE: str = "https://api.exa.ai"
    EXA_SEARCH_ENABLED: bool = False
    EXA_SEARCH_TIMEOUT_SEC: int = 30
    EXA_SEARCH_NUM_RESULTS: int = 5
    EXA_SEARCH_HIGHLIGHTS_MAX_CHARACTERS: int = 1200

    # 火山引擎联网搜索（API Key 接入）
    VOLC_SEARCH_API_KEY: str = ""
    VOLC_SEARCH_API_BASE: str = "https://open.feedcoopapi.com/search_api/web_search"
    VOLC_SEARCH_ENABLED: bool = False
    VOLC_SEARCH_TIMEOUT_SEC: int = 30
    VOLC_SEARCH_NUM_RESULTS: int = 5
    VOLC_SEARCH_TIME_RANGE: str = "OneYear"

    # 记忆系统
    MEMORY_ENABLED: bool = True
    MEMORY_VECTOR_ENABLED: bool = True
    MEMORY_DIR: str = "./memory_store"
    MEMORY_EMBEDDING_PROVIDER: str = "vivo"  # hash | dashscope | vivo
    MEMORY_EMBEDDING_DIMENSIONS: int = 1024
    MEMORY_EMBEDDING_BATCH_SIZE: int = 10
    MEMORY_EMBEDDING_TIMEOUT_SEC: int = 30
    MEMORY_TOP_K: int = 6
    MEMORY_MAX_DISTANCE: float = 0.9
    MEMORY_CHUNK_SIZE: int = 800
    MEMORY_CHUNK_OVERLAP: int = 100
    MEMORY_FAIL_OPEN: bool = True

    # 阿里云百炼 / 通义千问 Embedding
    DASHSCOPE_API_KEY: str = ""
    DASHSCOPE_EMBEDDING_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    DASHSCOPE_EMBEDDING_MODEL: str = "text-embedding-v4"

    # 火山引擎 Ark（OpenAI 兼容 chat/completions）
    ARK_API_KEY: str = ""
    ARK_BASE_URL: str = "https://ark.cn-beijing.volces.com/api/v3"
    ARK_DEEPSEEK_V4_FLASH_MODEL: str = "ep-20260603141535-z2l7c"
    ARK_DEEPSEEK_V4_PRO_MODEL: str = "ep-20260528104127-tn2f7"
    ARK_DOUBAO_MINI_MODEL: str = "ep-20260607122404-2m67p"
    ARK_GLM_4_7_MODEL: str = "ep-20260607122957-8jtq2"
    ARK_TIMEOUT_SEC: int = 90

    # AI 聊天后台自动路由与队列容量（Flash -> Doubao Mini -> GLM 4.7）
    CHAT_AI_GLOBAL_CONCURRENCY: int = 20
    CHAT_AI_FLASH_CONCURRENCY: int = 5
    CHAT_AI_DOUBAO_MINI_CONCURRENCY: int = 10
    CHAT_AI_GLM_4_7_CONCURRENCY: int = 5

    # 视觉理解模型（火山引擎 Ark）
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
