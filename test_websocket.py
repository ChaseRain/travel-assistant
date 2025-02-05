import asyncio
import websockets
import json

async def test_chat():
    uri = "ws://localhost:8000/chat/12345"  # 12345是示例passenger_id
    async with websockets.connect(uri) as websocket:
        # 发送测试消息
        await websocket.send("你好，我想查询航班信息")
        
        # 接收响应
        while True:
            response = await websocket.recv()
            print(f"收到响应: {response}")

asyncio.run(test_chat()) 