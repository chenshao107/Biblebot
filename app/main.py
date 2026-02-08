from fastapi import FastAPI
from app.api.routes import router
import uvicorn

app = FastAPI(title="Professional RAG Server")

app.include_router(router, prefix="/rag")

@app.get("/")
async def root():
    return {"message": "Professional RAG Server is running."}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
