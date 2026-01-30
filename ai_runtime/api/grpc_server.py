"""
gRPC Server for AI Runtime
Provides gRPC streaming interface for Go Platform integration
"""
import grpc
from concurrent import futures
import asyncio
import logging
from typing import AsyncIterator
import sys
import os

# Add parent directory to path for proto imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from proto import chat_service_pb2
from proto import chat_service_pb2_grpc
from .chat_service import ChatServiceImpl

logger = logging.getLogger(__name__)


class ChatServiceGRPC(chat_service_pb2_grpc.ChatServiceServicer):
    """gRPC service implementation for ChatService"""

    def __init__(self):
        self.chat_service = ChatServiceImpl()
        logger.info("gRPC Chat Service initialized")

    async def StreamChat(self, request, context):
        """
        gRPC streaming chat handler

        Args:
            request: ChatRequest protobuf message
            context: gRPC context

        Yields:
            ChatResponse protobuf messages
        """
        try:
            # Convert protobuf request to dict for internal processing
            internal_request = {
                'session_id': request.session_id,
                'user_id': request.user_id,
                'tenant_id': request.tenant_id,
                'message': request.message,
                'metadata': dict(request.metadata),
                'config': {
                    'model': request.config.model,
                    'temperature': request.config.temperature,
                    'max_tokens': request.config.max_tokens,
                    'use_rag': request.config.use_rag,
                    'use_agent': request.config.use_agent,
                    'tools': list(request.config.tools),
                }
            }

            # Stream from internal chat service
            async for response_dict in self.chat_service.stream_chat(internal_request):
                # Convert dict response to protobuf
                pb_response = chat_service_pb2.ChatResponse(
                    session_id=response_dict.get('session_id', ''),
                    message_id=response_dict.get('message_id', ''),
                    type=self._map_response_type(response_dict.get('type', 0)),
                    content=response_dict.get('content', ''),
                    error=response_dict.get('error', ''),
                    metadata=response_dict.get('metadata', {})
                )

                # Add token usage if present
                if 'token_usage' in response_dict and response_dict['token_usage']:
                    usage = response_dict['token_usage']
                    pb_response.token_usage.CopyFrom(
                        chat_service_pb2.TokenUsage(
                            prompt_tokens=usage.get('prompt_tokens', 0),
                            completion_tokens=usage.get('completion_tokens', 0),
                            total_tokens=usage.get('total_tokens', 0),
                            cost=usage.get('cost', 0.0)
                        )
                    )

                yield pb_response

        except Exception as e:
            logger.error(f"gRPC streaming error: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))

            # Yield error response
            yield chat_service_pb2.ChatResponse(
                session_id=request.session_id,
                type=chat_service_pb2.RESPONSE_TYPE_ERROR,
                error=str(e)
            )

    async def GetChatHistory(self, request, context):
        """gRPC chat history handler"""
        try:
            # Convert request
            internal_request = {
                'session_id': request.session_id,
                'limit': request.limit,
                'offset': request.offset
            }

            # Get history from internal service
            history_dict = await self.chat_service.get_chat_history(internal_request)

            # Convert to protobuf
            messages = []
            for msg in history_dict.get('messages', []):
                pb_msg = chat_service_pb2.ChatMessage(
                    id=msg.get('id', ''),
                    role=msg.get('role', ''),
                    content=msg.get('content', ''),
                    timestamp=msg.get('timestamp', 0)
                )
                messages.append(pb_msg)

            return chat_service_pb2.ChatHistoryResponse(
                messages=messages,
                total=history_dict.get('total', 0)
            )

        except Exception as e:
            logger.error(f"gRPC history error: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return chat_service_pb2.ChatHistoryResponse()

    def _map_response_type(self, type_int: int):
        """Map internal type to protobuf enum"""
        type_map = {
            0: chat_service_pb2.RESPONSE_TYPE_UNSPECIFIED,
            1: chat_service_pb2.RESPONSE_TYPE_CONTENT,
            2: chat_service_pb2.RESPONSE_TYPE_THINKING,
            3: chat_service_pb2.RESPONSE_TYPE_TOOL_CALL,
            4: chat_service_pb2.RESPONSE_TYPE_COMPLETE,
            5: chat_service_pb2.RESPONSE_TYPE_ERROR,
        }
        return type_map.get(type_int, chat_service_pb2.RESPONSE_TYPE_UNSPECIFIED)


async def run_grpc_server(host: str = "[::]", port: int = 50051):
    """
    Run the gRPC server with real implementation
    """
    logger.info("=" * 60)
    logger.info("Starting AI Runtime gRPC Server")
    logger.info("-" * 60)
    logger.info(f"  Host: {host}")
    logger.info(f"  Port: {port}")
    logger.info(f"  Status: Production Mode")
    logger.info("=" * 60)

    # Create gRPC server
    server = grpc.aio.server(
        futures.ThreadPoolExecutor(max_workers=10),
        options=[
            ('grpc.max_send_message_length', 50 * 1024 * 1024),  # 50MB
            ('grpc.max_receive_message_length', 50 * 1024 * 1024),
        ]
    )

    # Add service
    service = ChatServiceGRPC()
    chat_service_pb2_grpc.add_ChatServiceServicer_to_server(service, server)

    # Start server
    server.add_insecure_port(f'{host}:{port}')
    await server.start()

    logger.info(f"✅ gRPC Server running on {host}:{port}")
    logger.info("Press Ctrl+C to stop")

    try:
        await server.wait_for_termination()
    except asyncio.CancelledError:
        logger.info("gRPC server shutting down...")
        await server.stop(grace=5)
