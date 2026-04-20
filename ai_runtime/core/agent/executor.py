"""
Legacy compatibility executor.

The production runtime entrypoints use `ai_runtime.core.agent_runtime.*` and do not route
through this module anymore. Keep it importable for compatibility only.
"""

from typing import AsyncIterator, Dict, List, Optional, Callable, Any
from abc import ABC, abstractmethod
import json


class Tool(ABC):
    """Base tool interface for agents"""

    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description

    @abstractmethod
    async def execute(self, **kwargs) -> Any:
        """Execute the tool"""
        pass

    def to_schema(self) -> Dict:
        """Convert tool to schema format"""
        return {
            "name": self.name,
            "description": self.description
        }


class AgentResponse:
    """Agent response chunk"""

    def __init__(self,
                 content: str = "",
                 response_type: str = "content",
                 tool_call: Optional[Dict] = None,
                 finish_reason: Optional[str] = None,
                 usage: Optional[Dict] = None):
        self.content = content
        self.response_type = response_type  # content, thinking, tool_call, complete
        self.tool_call = tool_call
        self.finish_reason = finish_reason
        self.usage = usage or {}

    def __repr__(self):
        return f"AgentResponse(type={self.response_type}, content={self.content[:50]}...)"


class AgentExecutor:
    """Agent executor with tool support and streaming"""

    def __init__(self, llm, tools: Optional[List[Tool]] = None):
        self.llm = llm
        self.tools = {tool.name: tool for tool in (tools or [])}

    def register_tool(self, tool: Tool):
        """Register a tool"""
        self.tools[tool.name] = tool

    async def stream_execute(self,
                            messages: List[Dict[str, str]],
                            use_tools: bool = True,
                            **kwargs) -> AsyncIterator[AgentResponse]:
        """
        Execute agent with streaming

        Args:
            messages: Chat messages
            use_tools: Whether to enable tool usage
            **kwargs: Additional LLM parameters

        Yields:
            AgentResponse chunks
        """
        # Add tool descriptions to system prompt if tools are enabled
        if use_tools and self.tools:
            tool_descriptions = "\n".join(
                f"- {tool.name}: {tool.description}"
                for tool in self.tools.values()
            )
            system_message = {
                "role": "system",
                "content": f"You have access to the following tools:\n{tool_descriptions}\n\n"
                          f"To use a tool, respond with: TOOL_CALL: {{\"name\": \"tool_name\", \"args\": {{...}}}}"
            }
            messages = [system_message] + messages

        # Stream LLM response
        full_response = ""
        async for chunk in self.llm.stream_chat(messages, **kwargs):
            full_response += chunk.content

            # Check for tool calls in response
            if "TOOL_CALL:" in full_response:
                # Extract tool call
                try:
                    tool_call_str = full_response.split("TOOL_CALL:")[1].strip()
                    tool_call = json.loads(tool_call_str)

                    yield AgentResponse(
                        content="",
                        response_type="tool_call",
                        tool_call=tool_call
                    )

                    # Execute tool
                    tool_name = tool_call.get("name")
                    tool_args = tool_call.get("args", {})

                    if tool_name in self.tools:
                        result = await self.tools[tool_name].execute(**tool_args)
                        yield AgentResponse(
                            content=f"\n[Tool Result: {result}]\n",
                            response_type="content"
                        )
                    else:
                        yield AgentResponse(
                            content=f"\n[Error: Tool {tool_name} not found]\n",
                            response_type="content"
                        )

                    full_response = ""  # Reset for next iteration
                except json.JSONDecodeError:
                    # Not a complete tool call yet, continue streaming
                    pass

            # Regular content
            if chunk.content:
                yield AgentResponse(
                    content=chunk.content,
                    response_type="content"
                )

            # Handle completion
            if chunk.finish_reason:
                yield AgentResponse(
                    content="",
                    response_type="complete",
                    finish_reason=chunk.finish_reason,
                    usage=chunk.usage
                )
