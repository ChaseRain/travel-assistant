'use client';

import { useState } from 'react';
import ChatInput from '@/components/ChatInput';
import ChatMessages from '@/components/ChatMessages';
import { Message } from '@/types';

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);

  const handleSendMessage = async (content: string) => {
    setLoading(true);
    
    try {
      // 添加用户消息
      const userMessage: Message = {
        role: 'user',
        content,
        id: Date.now().toString()
      };
      
      setMessages(prev => [...prev, userMessage]);

      // 调用后端API
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message: content,
        }),
      });

      const data = await response.json();

      // 添加助手回复
      const assistantMessage: Message = {
        role: 'assistant',
        content: data.response,
        id: (Date.now() + 1).toString()
      };

      setMessages(prev => [...prev, assistantMessage]);
    } catch (error) {
      console.error('Error sending message:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="flex min-h-screen flex-col items-center p-4 bg-gray-100">
      <div className="w-full max-w-4xl bg-white rounded-lg shadow-lg overflow-hidden">
        <div className="p-4 bg-blue-600 text-white">
          <h1 className="text-2xl font-bold">Travel Assistant</h1>
        </div>
        
        <div className="h-[600px] overflow-y-auto p-4">
          <ChatMessages messages={messages} />
        </div>
        
        <div className="p-4 border-t">
          <ChatInput onSend={handleSendMessage} disabled={loading} />
        </div>
      </div>
    </main>
  );
} 