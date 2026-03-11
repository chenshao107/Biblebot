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
    EMBEDDING_API_TIMEOUT: int = 60  # API调用超时时间（秒）
    EMBEDDING_API_MAX_RETRIES: int = 3  # 最大重试次数
    EMBEDDING_API_RETRY_DELAY: int = 2  # 重试间隔（秒）

    # 重排 (Rerank) 配置
    # 智能启用：当检索结果数量超过 top_k 时自动启用 rerank
    RERANK_MODEL_NAME: str = "ms-marco-MiniLM-L-6-v2"
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
    
    # Agent 配置
    AGENT_MAX_ITERATIONS: int = 10  # Agent 最大迭代次数
    BASH_TOOL_TIMEOUT: int = 30  # Bash 命令超时时间（秒）
    PYTHON_TOOL_TIMEOUT: int = 30  # Python 执行超时时间（秒）
    BASH_WORK_DIR: Optional[str] = None  # Bash 工具工作目录，默认为 DATA_RAW_DIR
    
    # 对话历史配置
    CONVERSATION_MAX_HISTORY: int = 20  # 每个会话保留的最大对话轮数（一轮 = 用户+助手）
    CONVERSATION_MAX_MESSAGE_LENGTH: int = 500  # 单条消息在上下文中最大长度（字符）
    
    # 工具安全控制（调试期可禁用）
    ENABLE_BASH_WHITELIST: bool = False  # 是否启用 Bash 命令白名单检查，默认禁用方便调试
    ENABLE_PYTHON_RESTRICTIONS: bool = False  # 是否启用 Python 执行限制，默认禁用方便调试
    
    # LLM 调试配置
    DEBUG_LLM_API: bool = False  # 是否保存 LLM API 调用的输入输出到文件
    DEBUG_LLM_LOG_DIR: str = "logs/llm"  # LLM 调试日志保存目录
    
    # Docker 沙箱配置
    USE_DOCKER_SANDBOX: bool = True  # 是否使用 Docker 沙箱（推荐）
    DOCKER_SANDBOX_IMAGE: str = "bibobot-sandbox:latest"  # 沙箱镜像名
    DOCKER_MEMORY_LIMIT: str = "512m"  # Docker 内存限制
    DOCKER_CPU_QUOTA: int = 100000  # Docker CPU 限制（100000 = 1核）
    DOCKER_TIMEOUT: int = 60  # Docker 命令执行超时（秒）
    
    # 线程池配置（用于并发请求处理）
    THREAD_POOL_MAX_WORKERS: int = 32  # 线程池最大工作线程数，建议设置为预期并发数的 1-2 倍
    
    # MCP 服务器配置（JSON 格式）
    # 示例: {"filesystem": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "/data"]}, "fetch": {"command": "uvx", "args": ["mcp-server-fetch"]}}
    MCP_SERVERS_CONFIG: Optional[str] = None  # MCP 服务器配置 JSON 字符串
    ENABLE_MCP_TOOLS: bool = False  # 是否启用 MCP 工具

    # Pydantic 配置：自动读取 .env 文件
    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8", 
        extra="ignore"
    )

settings = Settings()
