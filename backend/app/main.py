from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from app.services.customer_support.graph import create_customer_support_graph
from datetime import datetime
import shutil
import uuid
from typing import List, Dict, Any, Optional

class ChatRequest(BaseModel):
    message: str
    thread_id: Optional[str] = None  # 修复类型提示

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # 替换为你的前端域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    """处理聊天请求的主函数"""
    try:
        graph = create_customer_support_graph()
        
        # 生成或使用现有的thread_id
        thread_id = request.thread_id or str(uuid.uuid4())
        
        # 添加默认用户信息
        user_info = {
            "id": "default_user",
            "name": "访客用户",
            "type": "customer",
            "language": "zh-CN"
        }
        
        # 创建一个包含完整上下文的消息历史
        message_history = [
            {
                "role": "user",
                "content": request.message
            }
        ]
        
        # 调用图时提供所有必需的变量
        events = graph.invoke(
            {
                "messages": message_history,
                "user_info": user_info,
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # 添加时间信息
            },
            {
                "configurable": {
                    "thread_id": thread_id,
                    "passenger_id": "3442 587242",
                    "checkpoint_id": "default",
                    "checkpoint_ns": "default"
                }
            }
        )
        
        if "messages" in events:
            messages = events["messages"]
            # 如果messages是列表，获取最后一条消息的内容
            if isinstance(messages, list) and messages:
                last_message = messages[-1]
                return {
                    "response": last_message.get("content", str(last_message))
                }
            # 如果是单个消息对象
            return {
                "response": messages.get("content", str(messages))
            }
            
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)