from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import uvicorn
import os

from app.services.chat_service import ChatService
from app.models.chat import ChatMessage, ChatResponse
from app.utils.config import Settings

app = FastAPI()
settings = Settings()

# 配置CORS中间件
# 允许跨域资源共享(CORS)配置
# - allow_origins: 允许的源域名列表,这里允许localhost:3000前端访问
# - allow_credentials: 允许发送认证信息(cookies等)
# - allow_methods: 允许的HTTP方法,*表示允许所有方法
# - allow_headers: 允许的HTTP头,*表示允许所有头部
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

chat_service = ChatService()

@app.post("/api/chat")
async def chat(message: ChatMessage) -> ChatResponse:
    try:
        response = await chat_service.process_message(message.message)
        return ChatResponse(response=response)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000) 