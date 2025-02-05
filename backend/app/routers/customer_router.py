from fastapi import APIRouter, HTTPException, Depends
from app.models.chat import ChatRequest, ChatResponse
from app.services.customer_support.graph import create_customer_support_graph
from langchain_core.messages import ToolMessage, HumanMessage, AIMessage
import uuid
from typing import Optional

# 第五部分 - API路由
router = APIRouter()
graph = create_customer_support_graph()

@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        thread_id = str(uuid.uuid4())
        
        # 转换消息格式为 LangChain 支持的格式
        converted_messages = []
        for msg in request.messages:
            if msg.role == "user":
                converted_messages.append(HumanMessage(content=msg.content))
            elif msg.role == "assistant":
                converted_messages.append(AIMessage(content=msg.content))

        config = {
            "configurable": {
                "passenger_id": request.passenger_id,
                "thread_id": thread_id,
            }
        }

        state = {
            "messages": converted_messages,
            "dialog_state": ["assistant"]
        }

        # 使用 invoke 而不是 stream 来获取响应
        result = graph.invoke(state, config)
        
        response = ""
        requires_confirmation = False
        action_details = None
        
        if "messages" in result:
            messages = result["messages"]
            if isinstance(messages, list) and len(messages) > 0:
                last_message = messages[-1]
                if hasattr(last_message, "content"):
                    response = last_message.content
                
                if hasattr(last_message, "tool_calls") and last_message.tool_calls:
                    requires_confirmation = True
                    action_details = last_message.tool_calls[0]
            elif hasattr(messages, "content"):
                # 处理单个消息的情况
                response = messages.content
                if hasattr(messages, "tool_calls") and messages.tool_calls:
                    requires_confirmation = True 
                    action_details = messages.tool_calls[0]

        return ChatResponse(
            response=response,
            requires_confirmation=requires_confirmation,
            action_details=action_details
        )

    except Exception as e:
        # 添加错误日志以便调试
        print(f"Error in chat endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/confirm-action")
async def confirm_action(
    thread_id: str,
    action_id: str,
    confirmed: bool,
    feedback: Optional[str] = None
):
    try:
        config = {
            "configurable": {
                "thread_id": thread_id
            }
        }
        
        if confirmed:
            result = graph.invoke(None, config)
        else:
            result = graph.invoke(
                {
                    "messages": [
                        ToolMessage(
                            tool_call_id=action_id,
                            content=f"Action denied by user. Reason: {feedback}"
                        )
                    ]
                },
                config
            )
            
        return {"status": "success", "result": result}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))