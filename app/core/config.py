from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    # Qdrant 配置
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_COLLECTION_NAME: str = "kb_hybrid"

    # LLM 配置
    LLM_API_KEY: Optional[str] = None
    LLM_BASE_URL: str = "https://api.deepseek.com/v1"
    LLM_MODEL: str = "deepseek-chat"

    # 词嵌入 (Embedding) 配置
    EMBEDDING_MODEL_NAME: str = "BAAI/bge-base-zh-v1.5"
    EMBEDDING_DIM: int = 768
    USE_EMBEDDING_API: bool = False
    EMBEDDING_API_KEY: Optional[str] = None
    EMBEDDING_API_URL: str = "https://api.siliconflow.cn/v1/embeddings"

    # 重排 (Rerank) 配置
    RERANK_MODEL_NAME: str = "ms-marco-MiniLM-L-6-v2"
    USE_RERANK_API: bool = False
    RERANK_API_KEY: Optional[str] = None
    RERANK_API_URL: str = "https://api.siliconflow.cn/v1/rerank"
    
    # 路径配置
    BASE_DIR: str = "."
    DATA_RAW_DIR: str = "data/raw"
    DATA_CANONICAL_DIR: str = "data/canonical_md"
    DATA_CHUNKS_DIR: str = "data/chunks"  # 切块中间文件
    DATA_EMBEDDINGS_DIR: str = "data/embeddings"  # 嵌入向量元数据
    
    # 中间文件保存配置
    SAVE_INTERMEDIATE_FILES: bool = True  # 是否保存中间文件用于调优

    # Pydantic 配置：自动读取 .env 文件
    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8", 
        extra="ignore"
    )

settings = Settings()
