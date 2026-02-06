from typing import AsyncIterator
import sys
import os

# Add proto path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../proto'))

from core.prompt import PromptBuilder
from core.rag import RAGPipeline, Retriever, SimpleVectorStore
from core.llm import LocalLLM, OpenAILLM, DeepseekLLM
from core.agent import AgentExecutor
from core.agent.tools import get_default_tools
from core.stream import StreamPipeline, TokenCounterMiddleware, CostTrackingMiddleware


class ChatServiceImpl:
    """Chat service implementation"""

    def __init__(self):
        self.prompt_builder = PromptBuilder()
        self.vector_store = SimpleVectorStore()
        self.retriever = Retriever(self.vector_store)
        self.rag_pipeline = RAGPipeline(self.retriever)

        # Initialize LLM (using Local for demo, can switch to OpenAI)
        self.llm = DeepseekLLM(model="deepseek-chat", api_key=os.getenv("DEEPSEEK_API_KEY"))


        # Initialize agent with tools
        self.agent = AgentExecutor(self.llm, tools=get_default_tools())

        # Stream pipeline
        self.stream_pipeline = StreamPipeline([
            TokenCounterMiddleware(),
            CostTrackingMiddleware()
        ])

        # Session storage (in-memory for demo)
        self.sessions = {}

    async def stream_chat(self, request) -> AsyncIterator:
        """
        Stream chat handler

        Args:
            request: ChatRequest protobuf message

        Yields:
            ChatResponse protobuf messages
        """
        session_id = request.session_id
        user_message = request.message
        config = request.config

        # Get or create session
        if session_id not in self.sessions:
            self.sessions[session_id] = {
                "history": [],
                "metadata": {}
            }

        session = self.sessions[session_id]

        try:
            # Build context with RAG if enabled
            context = None
            if config.use_rag:
                context = await self.rag_pipeline.process(user_message, top_k=3)

            # Build messages
            messages = self.prompt_builder.build(
                system_prompt="You are a helpful AI assistant.",
                user_message=user_message,
                context=context,
                history=session["history"]
            )

            # Execute with or without agent
            if config.use_agent:
                # Use agent executor
                stream_source = self.agent.stream_execute(
                    messages,
                    use_tools=True,
                    temperature=config.temperature or 0.7,
                    max_tokens=config.max_tokens or 2000
                )

                async for agent_response in stream_source:
                    # Yield response chunk
                    response_type = self._map_response_type(agent_response.response_type)

                    yield {
                        "session_id": session_id,
                        "message_id": f"msg_{session_id}_{len(session['history'])}",
                        "type": response_type,
                        "content": agent_response.content,
                        "metadata": {}
                    }

                    # Handle completion
                    if agent_response.finish_reason:
                        yield {
                            "session_id": session_id,
                            "message_id": f"msg_{session_id}_{len(session['history'])}",
                            "type": 4,  # COMPLETE
                            "content": "",
                            "token_usage": agent_response.usage,
                            "metadata": {}
                        }

            else:
                # Direct LLM streaming
                full_response = ""
                async for llm_chunk in self.llm.stream_chat(messages):
                    full_response += llm_chunk.content

                    yield {
                        "session_id": session_id,
                        "message_id": f"msg_{session_id}_{len(session['history'])}",
                        "type": 1,  # CONTENT
                        "content": llm_chunk.content,
                        "metadata": {}
                    }

                    # Handle completion
                    if llm_chunk.finish_reason:
                        yield {
                            "session_id": session_id,
                            "message_id": f"msg_{session_id}_{len(session['history'])}",
                            "type": 4,  # COMPLETE
                            "content": "",
                            "token_usage": llm_chunk.usage,
                            "metadata": {}
                        }

                # Update session history
                session["history"].append({"role": "user", "content": user_message})
                session["history"].append({"role": "assistant", "content": full_response})

        except Exception as e:
            # Error response
            yield {
                "session_id": session_id,
                "message_id": "",
                "type": 5,  # ERROR
                "content": "",
                "error": str(e),
                "metadata": {}
            }

    def _map_response_type(self, agent_type: str) -> int:
        """Map agent response type to protobuf enum"""
        mapping = {
            "content": 1,
            "thinking": 2,
            "tool_call": 3,
            "complete": 4,
            "error": 5
        }
        return mapping.get(agent_type, 1)

    async def get_chat_history(self, request):
        """Get chat history handler"""
        session_id = request.session_id
        session = self.sessions.get(session_id, {"history": []})

        messages = []
        history = session["history"]

        for i, msg in enumerate(history):
            messages.append({
                "id": f"msg_{i}",
                "role": msg.get("role", ""),
                "content": msg.get("content", ""),
                "timestamp": 0,
                "token_usage": {}
            })

        return {
            "messages": messages,
            "total": len(messages)
        }
