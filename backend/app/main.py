from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from app.services.customer_support.graph import create_customer_support_graph

class ChatRequest(BaseModel):
    message: str

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    """处理聊天请求的主函数"""
    try:
        graph = create_customer_support_graph()
        events = graph.invoke(
            {"messages": [{"role": "user", "content": request.message}]},
            {}
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