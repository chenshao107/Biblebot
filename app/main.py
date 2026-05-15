from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router
import uvicorn

app = FastAPI(
    title="Biblebot Knowledge Server",
    description="企业知识库 RAG 检索服务。Agent Runtime 支持 Qoder CLI / Claude CLI。",
    version="3.0.0"
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(router, prefix="/api")

@app.get("/")
async def root():
    return {
        "message": "Biblebot Knowledge Server is running.",
        "version": "3.0.0",
        "architecture": "轻RAG + 强探索",
        "agent_runtime": "Qoder CLI (default) / Claude CLI",
        "endpoints": {
            "rag": "/api/query - RAG 语义检索",
            "docs": "/docs - API 文档",
        },
        "cli_tools": {
            "rag_search": "python scripts/rag_search.py '查询词'",
        }
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
