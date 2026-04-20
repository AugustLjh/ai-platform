@echo off
echo Generating gRPC stubs for Python and Go...
echo.

REM Python
echo [1/2] Generating Python stubs...
python -m grpc_tools.protoc -I./proto --python_out=./ai_runtime/proto --grpc_python_out=./ai_runtime/proto ./proto/chat_service.proto
powershell -NoProfile -Command "(Get-Content 'ai_runtime/proto/chat_service_pb2_grpc.py') -replace '^import chat_service_pb2 as ','from . import chat_service_pb2 as ' | Set-Content 'ai_runtime/proto/chat_service_pb2_grpc.py'"
if %ERRORLEVEL% EQU 0 (
    echo     Python stubs generated successfully
) else (
    echo     ERROR: Failed to generate Python stubs
)
echo.

REM Go - using downloaded protoc or system protoc
echo [2/2] Generating Go stubs...

REM Try to find protoc
where protoc >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo     Using system protoc
    protoc --go_out=./platform --go-grpc_out=./platform --go_opt=paths=source_relative --go-grpc_opt=paths=source_relative --plugin=protoc-gen-go=%USERPROFILE%\go\bin\protoc-gen-go.exe --plugin=protoc-gen-go-grpc=%USERPROFILE%\go\bin\protoc-gen-go-grpc.exe ./proto/chat_service.proto
    if %ERRORLEVEL% EQU 0 (
        echo     Go stubs generated successfully
    ) else (
        echo     ERROR: Failed to generate Go stubs
    )
) else (
    echo     WARNING: protoc not found in PATH
    echo     Please install protoc: choco install protoc
    echo     Or download from: https://github.com/protocolbuffers/protobuf/releases
)

echo.
echo Done!
pause
