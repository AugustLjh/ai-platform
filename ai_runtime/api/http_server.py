"""
FastAPI HTTP Server for AI Runtime
Provides REST API and SSE streaming endpoints for development and testing
"""
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
import asyncio
import json
import logging

from .chat_service import ChatServiceImpl
from .documents import router as documents_router
from .knowledge_bases import router as kb_router

logger = logging.getLogger(__name__)


# Request/Response Models
class ChatConfig(BaseModel):
    """Chat configuration"""
    use_rag: bool = Field(default=False, description="Enable RAG")
    use_agent: bool = Field(default=False, description="Enable Agent")
    temperature: Optional[float] = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=2000, ge=1, le=8000)


class ChatRequest(BaseModel):
    """Chat request model"""
    session_id: str = Field(..., description="Session ID")
    message: str = Field(..., min_length=1, description="User message")
    config: ChatConfig = Field(default_factory=ChatConfig)


class ChatMessage(BaseModel):
    """Chat message model"""
    id: str
    role: str
    content: str
    timestamp: int
    token_usage: Dict[str, int] = Field(default_factory=dict)


class ChatHistoryResponse(BaseModel):
    """Chat history response"""
    session_id: str
    messages: List[ChatMessage]
    total: int


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    version: str
    services: Dict[str, str]


class ErrorResponse(BaseModel):
    """Error response"""
    error: str
    detail: Optional[str] = None


def create_http_app() -> FastAPI:
    """Create and configure FastAPI application"""

    app = FastAPI(
        title="AI Runtime API",
        description="FastAPI HTTP interface for AI Runtime - Development & Testing",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc"
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # In production, specify exact origins
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Initialize chat service
    chat_service = ChatServiceImpl()

    # Include routers
    app.include_router(kb_router)
    app.include_router(documents_router)

    @app.get("/", response_model=Dict[str, str])
    async def root():
        """Root endpoint"""
        return {
            "service": "AI Runtime HTTP Server",
            "version": "1.0.0",
            "docs": "/docs",
            "health": "/health",
            "knowledge_base": "/api/v1/knowledge"
        }

    @app.get("/health", response_model=HealthResponse)
    async def health_check():
        """Health check endpoint"""
        return {
            "status": "healthy",
            "version": "1.0.0",
            "services": {
                "llm": "ready",
                "rag": "ready",
                "agent": "ready"
            }
        }

    @app.post("/api/v1/chat", response_model=Dict[str, str])
    async def chat_complete(request: ChatRequest):
        """
        Non-streaming chat endpoint
        Returns complete response at once
        """
        try:
            full_response = ""

            # Convert to internal request format
            internal_request = type('Request', (), {
                'session_id': request.session_id,
                'message': request.message,
                'config': type('Config', (), {
                    'use_rag': request.config.use_rag,
                    'use_agent': request.config.use_agent,
                    'temperature': request.config.temperature,
                    'max_tokens': request.config.max_tokens
                })()
            })()

            # Collect all chunks
            async for chunk in chat_service.stream_chat(internal_request):
                if chunk.get("type") == 1:  # CONTENT
                    full_response += chunk.get("content", "")

            return {
                "session_id": request.session_id,
                "response": full_response
            }

        except Exception as e:
            logger.error(f"Chat error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/v1/chat/stream")
    async def chat_stream(request: ChatRequest):
        """
        Server-Sent Events (SSE) streaming chat endpoint
        Streams response in real-time
        """
        async def event_generator():
            try:
                # Convert to internal request format
                internal_request = type('Request', (), {
                    'session_id': request.session_id,
                    'message': request.message,
                    'config': type('Config', (), {
                        'use_rag': request.config.use_rag,
                        'use_agent': request.config.use_agent,
                        'temperature': request.config.temperature,
                        'max_tokens': request.config.max_tokens
                    })()
                })()

                # Stream responses
                async for chunk in chat_service.stream_chat(internal_request):
                    # Format as SSE
                    data = json.dumps(chunk)
                    yield f"data: {data}\n\n"
                    await asyncio.sleep(0.01)  # Small delay for stability

                # Send completion signal
                yield "data: [DONE]\n\n"

            except Exception as e:
                logger.error(f"Streaming error: {e}")
                error_data = json.dumps({"error": str(e)})
                yield f"data: {error_data}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )

    @app.get("/api/v1/chat/history/{session_id}", response_model=ChatHistoryResponse)
    async def get_chat_history(session_id: str):
        """Get chat history for a session"""
        try:
            # Convert to internal request format
            internal_request = type('Request', (), {
                'session_id': session_id
            })()

            history_data = await chat_service.get_chat_history(internal_request)

            return {
                "session_id": session_id,
                "messages": history_data.get("messages", []),
                "total": history_data.get("total", 0)
            }

        except Exception as e:
            logger.error(f"History retrieval error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.delete("/api/v1/chat/session/{session_id}")
    async def delete_session(session_id: str):
        """Delete a chat session"""
        try:
            if session_id in chat_service.sessions:
                del chat_service.sessions[session_id]
                return {"message": f"Session {session_id} deleted"}
            else:
                raise HTTPException(status_code=404, detail="Session not found")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Session deletion error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/v1/chat/sessions")
    async def list_sessions():
        """List all active sessions"""
        return {
            "sessions": list(chat_service.sessions.keys()),
            "total": len(chat_service.sessions)
        }

    return app


async def run_http_server(host: str = "0.0.0.0", port: int = 8000):
    """Run the HTTP server"""
    import uvicorn

    logger.info("=" * 60)
    logger.info("Starting AI Runtime HTTP Server (FastAPI)")
    logger.info("-" * 60)
    logger.info(f"  Host: {host}")
    logger.info(f"  Port: {port}")
    logger.info(f"  Docs: http://{host}:{port}/docs")
    logger.info(f"  API: http://{host}:{port}/api/v1/chat")
    logger.info("=" * 60)

    config = uvicorn.Config(
        create_http_app(),
        host=host,
        port=port,
        log_level="info"
    )
    server = uvicorn.Server(config)
    await server.serve()