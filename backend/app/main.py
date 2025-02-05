from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from app.services.customer_support.graph import create_customer_support_graph
from datetime import datetime
import shutil
import uuid
from typing import List, Dict, Any, Optional
from langchain.schema import HumanMessage
from langchain.schema import BaseMessage

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
        
        # 添加更详细的用户信息
        user_info = {
            "id": thread_id,
            "name": "访客用户",
            "type": "customer",
            "language": "zh-CN",
            "passenger_id": "3442 587242"
        }
        
        # 创建消息历史
        message_history = [
            HumanMessage(content=request.message)
        ]
        
        # 调用图并提供上下文
        events = graph.invoke(
            {
                "messages": message_history,
                "user_info": user_info,
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            },
            {
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_id": "default",
                    "checkpoint_ns": "default"
                }
            }
        )
        
        # 处理响应
        if isinstance(events, dict) and "messages" in events:
            ai_message = events["messages"]
            # 直接返回 content 属性
            return {"response": ai_message.content}
            
        return {"error": "无法获取有效响应"}
            
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)