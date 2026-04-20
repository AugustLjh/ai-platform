#!/bin/bash

# Generate gRPC stubs for both Python and Go

echo "Generating gRPC stubs..."

# Python
echo "Generating Python stubs..."
python3 -m grpc_tools.protoc \
  -I./proto \
  --python_out=./ai_runtime/proto \
  --grpc_python_out=./ai_runtime/proto \
  ./proto/chat_service.proto
sed -i 's/^import chat_service_pb2 as /from . import chat_service_pb2 as /' ./ai_runtime/proto/chat_service_pb2_grpc.py

# Go
echo "Generating Go stubs..."
mkdir -p ./platform/proto/chat
protoc \
  -I./proto \
  --go_out=./platform/proto/chat --go_opt=paths=source_relative \
  --go-grpc_out=./platform/proto/chat --go-grpc_opt=paths=source_relative \
  ./proto/chat_service.proto

echo "Done!"
