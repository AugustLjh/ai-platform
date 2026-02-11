#!/bin/bash

# Generate gRPC stubs for both Python and Go

echo "Generating gRPC stubs..."

# Python
echo "Generating Python stubs..."
cd ai_runtime
python3 -m grpc_tools.protoc \
  -I../proto \
  --python_out=. \
  --grpc_python_out=. \
  ../proto/chat_service.proto
cd ..

# Go
echo "Generating Go stubs..."
mkdir -p ./platform/proto/chat
protoc \
  -I./proto \
  --go_out=./platform/proto/chat --go_opt=paths=source_relative \
  --go-grpc_out=./platform/proto/chat --go-grpc_opt=paths=source_relative \
  ./proto/chat_service.proto

echo "Done!"
