#!/bin/bash

# Generate gRPC stubs for both Python and Go

echo "Generating gRPC stubs..."

# Python
echo "Generating Python stubs..."
cd ai_runtime
python -m grpc_tools.protoc \
  -I../proto \
  --python_out=. \
  --grpc_python_out=. \
  ../proto/chat_service.proto
cd ..

# Go
echo "Generating Go stubs..."
protoc \
  --go_out=./platform \
  --go-grpc_out=./platform \
  ./proto/chat_service.proto

echo "Done!"
