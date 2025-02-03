import os
from typing import Dict, Any
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_anthropic import ChatAnthropic
from langchain.chains import LLMChain
from langchain.prompts import ChatPromptTemplate

class ChatService:
    def __init__(self):
        self.llm = ChatAnthropic(
            model="claude-3-sonnet-20240229",
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY")
        )
        
        self.primary_assistant_prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a helpful customer support assistant for Swiss Airlines. "
                      "You help customers with flight bookings, travel arrangements, and general inquiries."),
            ("human", "{message}")
        ])
        
        self.chain = LLMChain(llm=self.llm, prompt=self.primary_assistant_prompt)

    async def process_message(self, message: str) -> str:
        try:
            response = await self.chain.ainvoke({"message": message})
            return response["text"]
        except Exception as e:
            print(f"Error processing message: {e}")
            raise e 