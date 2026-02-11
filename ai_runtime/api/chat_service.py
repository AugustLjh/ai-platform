from typing import AsyncIterator, Optional
import logging
import sys
import os

# Add proto path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../proto'))

from core.prompt import PromptBuilder
from core.rag import RAGPipeline, Retriever, SimpleVectorStore
from core.rag.retriever import DatabaseVectorStore
from core.llm import LocalLLM, OpenAILLM, DeepseekLLM
from core.agent import AgentExecutor
from core.agent.tools import get_default_tools
from core.stream import StreamPipeline, TokenCounterMiddleware, CostTrackingMiddleware
from core.dependencies import get_container

logger = logging.getLogger(__name__)


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

    def _build_rag_pipeline(self, tenant_id: str, user_id: Optional[str], knowledge_base_id: Optional[str]) -> RAGPipeline:
        """Build a RAG pipeline with database-backed retriever when available."""
        try:
            container = get_container()
            kb_service = container.kb_service
            vector_store = DatabaseVectorStore(
                kb_service=kb_service,
                tenant_id=tenant_id,
                user_id=user_id,
                knowledge_base_id=knowledge_base_id,
            )
            retriever = Retriever(vector_store)
            return RAGPipeline(retriever)
        except Exception as exc:
            logger.warning("RAG pipeline fallback to in-memory store: %s", exc)
            return self.rag_pipeline

    def _get_field(self, obj, key, default=None):
        """Support both dict and attribute-style request objects."""
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    def _get_config_field(self, config, key, default=None):
        """Support both dict and attribute-style config objects."""
        if config is None:
            return default
        if isinstance(config, dict):
            return config.get(key, default)
        return getattr(config, key, default)

    async def stream_chat(self, request) -> AsyncIterator:
        """
        Stream chat handler

        Args:
            request: ChatRequest protobuf message

        Yields:
            ChatResponse protobuf messages
        """
        session_id = self._get_field(request, "session_id")
        user_message = self._get_field(request, "message")
        config = self._get_field(request, "config")
        use_rag = bool(self._get_config_field(config, "use_rag", False))
        use_agent = bool(self._get_config_field(config, "use_agent", False))
        temperature = self._get_config_field(config, "temperature", 0.7) or 0.7
        max_tokens = self._get_config_field(config, "max_tokens", 2000) or 2000
        knowledge_base_id = self._get_config_field(config, "knowledge_base_id", None)
        if knowledge_base_id == "":
            knowledge_base_id = None
        metadata = self._get_field(request, "metadata", {}) or {}
        if not knowledge_base_id and isinstance(metadata, dict):
            knowledge_base_id = metadata.get("knowledge_base_id") or None
        tenant_id = self._get_field(request, "tenant_id", "default-tenant") or "default-tenant"
        user_id = self._get_field(request, "user_id", None) or None

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
            if use_rag:
                rag_pipeline = self._build_rag_pipeline(tenant_id, user_id, knowledge_base_id)
                context = await rag_pipeline.process(user_message, top_k=3)

            # Build messages
            messages = self.prompt_builder.build(
                system_prompt="You are a helpful AI assistant.",
                user_message=user_message,
                context=context,
                history=session["history"]
            )

            # Execute with or without agent
            if use_agent:
                # Use agent executor
                stream_source = self.agent.stream_execute(
                    messages,
                    use_tools=True,
                    temperature=temperature,
                    max_tokens=max_tokens
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
        session_id = self._get_field(request, "session_id")
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
