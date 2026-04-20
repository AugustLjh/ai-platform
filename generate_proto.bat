@echo off
REM Generate gRPC stubs for both Python and Go

echo Generating gRPC stubs...

REM Create output directories
if not exist ai_runtime\proto mkdir ai_runtime\proto
if not exist platform\proto\chat mkdir platform\proto\chat

REM Python stubs
echo Generating Python stubs...
python -m grpc_tools.protoc -I./proto --python_out=./ai_runtime/proto --grpc_python_out=./ai_runtime/proto ./proto/chat_service.proto
powershell -NoProfile -Command "(Get-Content 'ai_runtime/proto/chat_service_pb2_grpc.py') -replace '^import chat_service_pb2 as ','from . import chat_service_pb2 as ' | Set-Content 'ai_runtime/proto/chat_service_pb2_grpc.py'"
echo. > ai_runtime\proto\__init__.py

REM Go stubs
echo Generating Go stubs...
protoc --go_out=./platform --go_opt=paths=source_relative --go-grpc_out=./platform --go-grpc_opt=paths=source_relative -I./proto ./proto/chat_service.proto

echo Done!
echo Python: ai_runtime/proto/chat_service_pb2.py
echo Python: ai_runtime/proto/chat_service_pb2_grpc.py
echo Go: platform/proto/chat/chat_service.pb.go
echo Go: platform/proto/chat/chat_service_grpc.pb.go
