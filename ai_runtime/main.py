"""
AI Runtime Main Entry Point
Runs both gRPC and HTTP/FastAPI servers concurrently
"""
import asyncio
import logging
import sys
import os
from typing import Literal

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api.grpc_server import run_grpc_server
from api.http_server import run_http_server
from core.config import load_env_file, get_config
from core.database import init_db_manager, get_db_manager
from core.dependencies import init_container, get_container

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def print_banner():
    """Print startup banner"""
    print("\n" + "=" * 70)
    print("  ___    ___   ___  _   _ _   _ _____ ___ __  __ _____")
    print(" / _ \\  |_ _| | _ \\| | | | \\ | |_   _|_ _|  \\/  | ____|")
    print("| |_| |  | |  |   /| | | |  \\| | | |  | || |\\/| |  _|")
    print("|  _  |  | |  | | \\| |_| | |\\  | | |  | || |  | | |___")
    print("|_| |_| |___| |_| \\_\\___/|_| \\_| |_| |___|_|  |_|_____|")
    print("")
    print("         AI Runtime - Production Grade Server")
    print("=" * 70)


async def initialize_services():
    """Initialize all services"""
    logger.info("=" * 70)
    logger.info("[INIT] Initializing AI Runtime")
    logger.info("=" * 70)

    # Load environment variables
    load_env_file()

    # Load configuration
    config = get_config()
    config.print_summary()

    # Initialize database
    logger.info("\n[DB] Database Connection")
    logger.info("-" * 70)
    db_manager = init_db_manager(config.database)
    await db_manager.connect()

    # Health check
    logger.info("   Running health check...")
    healthy = await db_manager.health_check()
    if not healthy:
        raise RuntimeError("Database health check failed!")
    logger.info("   [OK] Database connection healthy")

    # Initialize services
    logger.info("\n[SERVICE] Service Initialization")
    logger.info("-" * 70)
    container = init_container()
    await container.initialize(config, db_manager)

    logger.info("\n" + "=" * 70)
    logger.info("[OK] All systems ready!")
    logger.info("=" * 70)

    return config


async def shutdown_services():
    """Cleanup on shutdown"""
    logger.info("\n" + "=" * 70)
    logger.info("[SHUTDOWN] Shutting down gracefully...")
    logger.info("=" * 70)

    try:
        db_manager = get_db_manager()
        await db_manager.disconnect()
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")

    logger.info("[BYE] Goodbye!")


async def run_both_servers(http_port: int = 8000, grpc_port: int = 50051):
    """Run both HTTP and gRPC servers concurrently"""
    print_banner()

    # Initialize services
    config = await initialize_services()

    logger.info("\n[SERVER] Starting Servers")
    logger.info("=" * 70)

    # Create tasks for both servers
    http_task = asyncio.create_task(run_http_server(host=config.server.host, port=http_port))
    grpc_task = asyncio.create_task(run_grpc_server(host="[::]", port=grpc_port))

    logger.info("\n" + "=" * 70)
    logger.info("[OK] Servers Running!")
    logger.info("=" * 70)
    logger.info(f"\n[HTTP] HTTP/REST API:")
    logger.info(f"   - Docs:      http://localhost:{http_port}/docs")
    logger.info(f"   - Health:    http://localhost:{http_port}/health")
    logger.info(f"   - Chat:      http://localhost:{http_port}/api/v1/chat")
    logger.info(f"   - Knowledge: http://localhost:{http_port}/api/v1/knowledge/documents")
    logger.info(f"\n[GRPC] gRPC API:")
    logger.info(f"   - Address:   localhost:{grpc_port}")
    logger.info("\n" + "=" * 70)
    logger.info("\n[INFO] Press Ctrl+C to stop")
    logger.info("")

    # Wait for both servers
    try:
        await asyncio.gather(http_task, grpc_task)
    except asyncio.CancelledError:
        pass
    finally:
        await shutdown_services()


async def run_http_only(port: int = 8000):
    """Run only HTTP server"""
    print_banner()

    # Initialize services
    config = await initialize_services()

    logger.info("\n[SERVER] Starting HTTP Server")
    logger.info("=" * 70)

    try:
        await run_http_server(host=config.server.host, port=port)
    finally:
        await shutdown_services()


async def run_grpc_only(port: int = 50051):
    """Run only gRPC server"""
    print_banner()

    # Initialize services
    config = await initialize_services()

    logger.info("\n[SERVER] Starting gRPC Server")
    logger.info("=" * 70)

    try:
        await run_grpc_server(host="[::]", port=port)
    finally:
        await shutdown_services()


def main(
    mode: Literal["both", "http", "grpc"] = "both",
    http_port: int = 8000,
    grpc_port: int = 50051
):
    """
    Main entry point

    Args:
        mode: Server mode - 'both', 'http', or 'grpc'
        http_port: HTTP server port (default: 8000)
        grpc_port: gRPC server port (default: 50051)
    """
    try:
        if mode == "both":
            asyncio.run(run_both_servers(http_port, grpc_port))
        elif mode == "http":
            asyncio.run(run_http_only(http_port))
        elif mode == "grpc":
            asyncio.run(run_grpc_only(grpc_port))
        else:
            logger.error(f"Unknown mode: {mode}. Use 'both', 'http', or 'grpc'")
            sys.exit(1)
    except KeyboardInterrupt:
        logger.info("\n\n[OK] Clean shutdown complete")
    except Exception as e:
        logger.error(f"\n[ERROR] Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="AI Runtime Server")
    parser.add_argument(
        "--mode",
        choices=["both", "http", "grpc"],
        default="both",
        help="Server mode (default: both)"
    )
    parser.add_argument(
        "--http-port",
        type=int,
        default=8000,
        help="HTTP server port (default: 8000)"
    )
    parser.add_argument(
        "--grpc-port",
        type=int,
        default=50051,
        help="gRPC server port (default: 50051)"
    )

    args = parser.parse_args()
    main(mode=args.mode, http_port=args.http_port, grpc_port=args.grpc_port)
