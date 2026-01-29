"""
gRPC Server for AI Runtime
Provides gRPC streaming interface for Go Platform integration
"""
import grpc
from concurrent import futures
import asyncio
import logging
from typing import AsyncIterator

from .chat_service import ChatServiceImpl

logger = logging.getLogger(__name__)


class ChatServiceGRPC:
    """gRPC service wrapper for ChatServiceImpl"""

    def __init__(self):
        self.chat_service = ChatServiceImpl()
        logger.info("gRPC Chat Service initialized")

    async def StreamChat(self, request, context):
        """
        gRPC streaming chat handler

        Note: This is a placeholder for proper gRPC implementation
        Full implementation requires:
        1. Generate proto stubs: python -m grpc_tools.protoc ...
        2. Import generated pb2 and pb2_grpc files
        3. Implement proper servicer class
        """
        try:
            async for response in self.chat_service.stream_chat(request):
                # In real implementation, convert dict to protobuf message
                yield response
        except Exception as e:
            logger.error(f"gRPC streaming error: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))

    async def GetChatHistory(self, request, context):
        """gRPC chat history handler"""
        try:
            return await self.chat_service.get_chat_history(request)
        except Exception as e:
            logger.error(f"gRPC history error: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))


async def run_grpc_server(host: str = "[::]", port: int = 50051):
    """
    Run the gRPC server

    Note: This is a mock implementation for demonstration
    Full implementation requires proto files to be compiled
    """
    logger.info("=" * 60)
    logger.info("Starting AI Runtime gRPC Server")
    logger.info("-" * 60)
    logger.info(f"  Host: {host}")
    logger.info(f"  Port: {port}")
    logger.info(f"  Status: Mock Mode (proto compilation needed)")
    logger.info("=" * 60)
    logger.info("")
    logger.info("To enable full gRPC functionality:")
    logger.info("1. Install: pip install grpcio grpcio-tools")
    logger.info("2. Generate stubs: python -m grpc_tools.protoc -I../proto --python_out=. --grpc_python_out=. ../proto/chat_service.proto")
    logger.info("3. Import generated stubs in this file")
    logger.info("")

    # Initialize service
    service = ChatServiceGRPC()

    # In a real implementation, you would:
    # server = grpc.aio.server()
    # chat_service_pb2_grpc.add_ChatServiceServicer_to_server(service, server)
    # server.add_insecure_port(f'{host}:{port}')
    # await server.start()
    # await server.wait_for_termination()

    # For now, just keep the "server" running
    logger.info(f"gRPC Server mock is running on {host}:{port}")
    logger.info("Press Ctrl+C to stop")

    try:
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        logger.info("gRPC server shutting down...")