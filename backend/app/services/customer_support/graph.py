from langgraph.graph import StateGraph
from langgraph.prebuilt import ToolNode
from langchain_anthropic import ChatAnthropic
from app.core.config import settings

# 从tools模块导入所需的工具函数
from .tools import (
    primary_tools,
    safe_tools,
    sensitive_tools,
    route_tools,
    get_user_info as user_info
)
from app.services.customer_support.prompts import primary_assistant_prompt

# 初始化LLM
llm = ChatAnthropic(
    model="claude-3-sonnet-20240229",
    api_key=settings.ANTHROPIC_API_KEY
)

class Assistant:
    def __init__(self, runnable):
        self.runnable = runnable

    def __call__(self, state, config):
        while True:
            result = self.runnable.invoke(state)
            if not result.tool_calls and (
                not result.content
                or isinstance(result.content, list)
                and not result.content[0].get("text")
            ):
                messages = state["messages"] + [("user", "Respond with a real output.")]
                state = {**state, "messages": messages}
            else:
                break
        return {"messages": result}

def create_customer_support_graph():
    # 定义图
    builder = StateGraph()
    
    # 添加节点
    builder.add_node("fetch_user_info", user_info)
    builder.add_node("assistant", Assistant(primary_assistant_prompt | llm.bind_tools(primary_tools)))
    builder.add_node("safe_tools", ToolNode(safe_tools))
    builder.add_node("sensitive_tools", ToolNode(sensitive_tools))
    
    # 添加边
    builder.add_edge("START", "fetch_user_info")
    builder.add_edge("fetch_user_info", "assistant")
    builder.add_conditional_edges(
        "assistant",
        route_tools,
        ["safe_tools", "sensitive_tools", "END"]
    )
    builder.add_edge("safe_tools", "assistant")
    builder.add_edge("sensitive_tools", "assistant")
    
    return builder.compile()
