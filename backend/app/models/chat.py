from pydantic import BaseModel
from typing import List, Optional, Union, Dict
from datetime import datetime

# 第三部分 - 提示词和助手定义
class ChatMessage(BaseModel):
    role: str
    content: str
    tool_calls: Optional[List[Dict]] = None

class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    passenger_id: Optional[str] = None

class ChatResponse(BaseModel):
    response: str
    requires_confirmation: bool = False
    action_details: Optional[dict] = None

class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict