from fastapi import APIRouter, HTTPException, Depends
from app.models.chat import ChatRequest, ChatResponse
from app.services.customer_support.graph import create_customer_support_graph
from langchain_core.messages import ToolMessage, HumanMessage, AIMessage
import uuid
import shutil
from typing import Optional

# Example conversation data
tutorial_questions = [
    "Hi there, what time is my flight?",
    "Am i allowed to update my flight to something sooner? I want to leave later today.",
    "Update my flight to sometime next week then",
    "The next available option is great",
    "what about lodging and transportation?",
    "Yeah i think i'd like an affordable hotel for my week-long stay (7 days). And I'll want to rent a car.",
    "OK could you place a reservation for your recommended hotel? It sounds nice.",
    "yes go ahead and book anything that's moderate expense and has availability.",
    "Now for a car, what are my options?",
    "Awesome let's just get the cheapest option. Go ahead and book for 7 days",
    "Cool so now what recommendations do you have on excursions?",
    "Are they available while I'm there?",
    "interesting - i like the museums, what options are there? ",
    "OK great pick one and book it for my second day there.",
]

# 第五部分 - API路由
router = APIRouter()
graph = create_customer_support_graph()

def _convert_messages(messages):
    return [
        HumanMessage(content=msg.content) if msg.role == "user"
        else AIMessage(content=msg.content)
        for msg in messages
    ]

def _process_result(messages):
    response = ""
    requires_confirmation = False
    action_details = None
    
    if isinstance(messages, list) and messages:
        last_message = messages[-1]
    else:
        last_message = messages
        
    if hasattr(last_message, "content"):
        response = last_message.content
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        requires_confirmation = True
        action_details = last_message.tool_calls[0]
        
    return response, requires_confirmation, action_details

@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        thread_id = str(uuid.uuid4())
        converted_messages = _convert_messages(request.messages)
        
        config = {
            "configurable": {
                "passenger_id": "3442 587242",
                "thread_id": thread_id,
            }
        }
        
        
        result = graph.invoke(
            {"messages": converted_messages, "dialog_state": ["assistant"]},
            config
        )
        
        response, requires_confirmation, action_details = _process_result(result.get("messages"))
        
        return ChatResponse(
            response=response,
            requires_confirmation=requires_confirmation,
            action_details=action_details,
            ai_message=result.get("messages") if isinstance(result.get("messages"), AIMessage) else None,
            tool_calls=getattr(result.get("messages"), "tool_calls", None)
        )

    except Exception as e:
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