from __future__ import annotations

import ast
import operator
from datetime import datetime, timezone
from typing import Any, Dict

from ai_runtime.core.agent_runtime.tools.base import BaseTool, ToolContext, ToolSpec


class GetCurrentTimeTool(BaseTool):
    spec = ToolSpec(
        name="get_current_time",
        description="Return the current UTC timestamp and ISO datetime.",
        input_schema={"type": "object", "properties": {}},
    )

    async def execute(self, context: ToolContext, arguments: Dict[str, Any]) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        return {
            "unix": int(now.timestamp()),
            "iso": now.isoformat(),
            "timezone": "UTC",
        }


class CalculatorTool(BaseTool):
    spec = ToolSpec(
        name="calculator",
        description="Evaluate a basic arithmetic expression.",
        input_schema={
            "type": "object",
            "required": ["expression"],
            "properties": {
                "expression": {"type": "string"},
            },
        },
    )

    _binary_operators = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
    }
    _unary_operators = {
        ast.UAdd: operator.pos,
        ast.USub: operator.neg,
    }

    def _evaluate(self, node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return self._evaluate(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in self._binary_operators:
            left = self._evaluate(node.left)
            right = self._evaluate(node.right)
            return float(self._binary_operators[type(node.op)](left, right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in self._unary_operators:
            operand = self._evaluate(node.operand)
            return float(self._unary_operators[type(node.op)](operand))
        raise ValueError("Unsupported expression")

    async def execute(self, context: ToolContext, arguments: Dict[str, Any]) -> Dict[str, Any]:
        expression = str(arguments.get("expression", "")).strip()
        if not expression:
            raise ValueError("expression is required")
        parsed = ast.parse(expression, mode="eval")
        value = self._evaluate(parsed)
        return {"expression": expression, "result": value}


class EchoJSONTool(BaseTool):
    spec = ToolSpec(
        name="echo_json",
        description="Return the provided JSON payload without modification.",
        input_schema={
            "type": "object",
            "properties": {
                "payload": {},
            },
        },
    )

    async def execute(self, context: ToolContext, arguments: Dict[str, Any]) -> Dict[str, Any]:
        payload: Any = arguments.get("payload", arguments)
        return {"payload": payload}


def register_builtin_tools(registry) -> None:
    registry.register(GetCurrentTimeTool())
    registry.register(CalculatorTool())
    registry.register(EchoJSONTool())
