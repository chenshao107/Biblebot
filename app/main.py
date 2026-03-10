from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router
import uvicorn

app = FastAPI(
    title="Knowledge Agent Server",
    description="基于 Agent 的智能知识服务，支持 RAG 检索、Bash 命令和 Python 执行",
    version="2.0.0"
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# OpenAI 兼容接口（根路径，供外部 UI 使用）
app.include_router(router)

# 原有 API（保留兼容）
app.include_router(router, prefix="/api")

@app.get("/")
async def root():
    return {
        "message": "Knowledge Agent Server is running.",
        "version": "2.0.0",
        "endpoints": {
            "agent": "/api/agent - Agent 查询（主推）",
            "rag": "/api/query - RAG 检索（快速）"
        }
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
