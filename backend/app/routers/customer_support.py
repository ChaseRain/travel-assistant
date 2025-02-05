from fastapi import APIRouter, HTTPException, Depends
from app.models.chat import ChatRequest, ChatResponse
from app.services.customer_support.graph import create_customer_support_graph
import uuid

# 第五部分 - API路由
router = APIRouter()
graph = create_customer_support_graph()

@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        thread_id = str(uuid.uuid4())
        
        config = {
            "configurable": {
                "passenger_id": request.passenger_id,
                "thread_id": thread_id,
            }
        }

        state = {
            "messages": request.messages,
            "dialog_state": ["assistant"]
        }

        events = graph.stream(
            state,
            config,
            stream_mode="values"
        )

        response = ""
        requires_confirmation = False
        action_details = None
        
        for event in events:
            if "messages" in event:
                last_message = event["messages"][-1]
                if hasattr(last_message, "content"):
                    response = last_message.content
                
                if hasattr(last_message, "tool_calls"):
                    requires_confirmation = True
                    action_details = last_message.tool_calls[0]

        return ChatResponse(
            response=response,
            requires_confirmation=requires_confirmation,
            action_details=action_details
        )

    except Exception as e:
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