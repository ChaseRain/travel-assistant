from typing import Annotated
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END 
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.memory import MemorySaver
from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    BaseMessage,
    ToolMessage
)
from langchain_core.runnables import RunnableLambda
from datetime import datetime
from app.core.config import settings
from .tools import (
    check_flight_status,
    get_available_seats,
    update_ticket_to_new_flight,
    cancel_ticket,
    search_hotels,
    book_hotel,
    update_hotel,
    cancel_hotel,
    search_car_rentals,
    book_car_rental,
    update_car_rental,
    cancel_car_rental,
    search_trip_recommendations,
    book_excursion,
    update_excursion,
    cancel_excursion,
    lookup_policy,
    handle_tool_error
)

# 定义状态- 消息构成了聊天历史记录，这是我们简单助手所需的所有状态
class State(TypedDict):
    messages: list[BaseMessage]

# 定义助手类-此函数接收图状态，将其格式化为提示，然后调用 LLM 以预测最佳响应
class Assistant:
    def __init__(self, runnable):
        self.runnable = runnable
        
    def __call__(self, state, config):
        while True:
            result = self.runnable.invoke(state)
            # 如果结果没有工具调用，并且没有内容，或者内容是一个列表，并且列表的第一个元素没有文本
            if not result.tool_calls and (
                not result.content 
                or isinstance(result.content, list)
                and not result.content[0].get("text")
            ):
                # 如果结果没有工具调用，并且没有内容，或者内容是一个列表，并且列表的第一个元素没有文本，则添加一个用户消息，提示助手提供一个真实的输出
                messages = state["messages"] + [HumanMessage(content="Respond with a real output.")]
                state = {**state, "messages": messages}
            else:
                break
        return {"messages": result}

# 初始化 LLM
llm = ChatAnthropic(
    model="claude-3-sonnet-20240229",
    api_key=settings.ANTHROPIC_API_KEY
)

# 修改提示词模板
primary_assistant_prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are a helpful customer support assistant for Swiss Airlines. "
        "Use the provided tools to search for flights, company policies, and other information to assist the user's queries. "
        "When searching, be persistent. Expand your query bounds if the first search returns no results. "
        "If a search comes up empty, expand your search before giving up."
        "\n\nCurrent user info: {user_info}"
        "\nCurrent time: {time}."
    ),
    MessagesPlaceholder(variable_name="messages")
])

# 定义工具列表
tools = [
    check_flight_status,
    get_available_seats,
    update_ticket_to_new_flight,
    cancel_ticket,
    search_hotels,
    book_hotel,
    update_hotel,
    cancel_hotel,
    search_car_rentals,
    book_car_rental,
    update_car_rental,
    cancel_car_rental,
    search_trip_recommendations,
    book_excursion,
    update_excursion,
    cancel_excursion,
    lookup_policy
]

def handle_tool_error(state: dict) -> dict:
    """处理工具执行错误的函数
    
    Args:
        state: 包含错误信息和工具调用的状态字典
        
    Returns:
        包含错误消息的字典
    """
    error = state.get("error")
    tool_calls = state["messages"][-1].tool_calls
    return {
        "messages": [
            ToolMessage(
                content=f"错误：{repr(error)}\n请修正你的错误。",
                tool_call_id=tc["id"],
            )
            for tc in tool_calls
        ]
    }

def create_tool_node_with_fallback(tools: list) -> ToolNode:
    """创建带有错误处理的工具节点
    
    Args:
        tools: 工具列表
        
    Returns:
        配置了错误处理的 ToolNode 实例
    """
    return ToolNode(tools).with_fallbacks(
        [RunnableLambda(handle_tool_error)],
        exception_key="error"
    )

def _print_event(
    event: dict, 
    _printed: set, 
    max_length: int = 1500
) -> None:
    """打印事件信息
    
    Args:
        event: 事件字典
        _printed: 已打印消息ID集合
        max_length: 消息最大长度
    """
    current_state = event.get("dialog_state")
    if current_state:
        print("当前状态：", current_state[-1])
    
    message = event.get("messages")
    if message:
        if isinstance(message, list):
            message = message[-1]
        if message.id not in _printed:
            msg_repr = message.pretty_repr(html=True)
            if len(msg_repr) > max_length:
                msg_repr = f"{msg_repr[:max_length]} ... (已截断)"
            print(msg_repr)
            _printed.add(message.id)

# 创建客服支持图
def create_customer_support_graph():
    """创建客服支持图"""
    # 创建图实例
    builder = StateGraph(State)
    
    # 创建助手实例
    assistant_runnable = primary_assistant_prompt | llm.bind_tools(tools)
    
    # 添加节点
    builder.add_node("assistant", Assistant(assistant_runnable))
    builder.add_node("tools", create_tool_node_with_fallback(tools))
    
    # 添加边
    builder.add_edge(START, "assistant")
    builder.add_conditional_edges(
        "assistant",
        tools_condition,
    )
    builder.add_edge("tools", "assistant")
    
    # 添加状态持久化
    memory = MemorySaver()
    
    return builder.compile(checkpointer=memory)
