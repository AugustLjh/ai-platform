@echo off
REM Generate gRPC stubs for both Python and Go

echo Generating gRPC stubs...

REM Create output directories
if not exist ai_runtime\proto mkdir ai_runtime\proto
if not exist platform\proto\chat mkdir platform\proto\chat

REM Python stubs
echo Generating Python stubs...
cd ai_runtime
python -m grpc_tools.protoc -I../proto --python_out=./proto --grpc_python_out=./proto ../proto/chat_service.proto
echo. > proto\__init__.py
cd ..

REM Go stubs
echo Generating Go stubs...
protoc --go_out=./platform --go_opt=paths=source_relative --go-grpc_out=./platform --go-grpc_opt=paths=source_relative -I./proto ./proto/chat_service.proto

echo Done!
echo Python: ai_runtime/proto/chat_service_pb2.py
echo Python: ai_runtime/proto/chat_service_pb2_grpc.py
echo Go: platform/proto/chat/chat_service.pb.go
echo Go: platform/proto/chat/chat_service_grpc.pb.go
