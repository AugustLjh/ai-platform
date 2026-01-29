from typing import Any
from core.agent.executor import Tool
import datetime


class TimeTools:
    """Time-related tools"""

    @staticmethod
    def get_current_time_tool() -> Tool:
        """Get current time tool"""

        class CurrentTimeTool(Tool):
            def __init__(self):
                super().__init__(
                    name="get_current_time",
                    description="Get the current date and time"
                )

            async def execute(self, **kwargs) -> str:
                return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        return CurrentTimeTool()


class CalculatorTools:
    """Calculator tools"""

    @staticmethod
    def get_calculator_tool() -> Tool:
        """Get calculator tool"""

        class CalculatorTool(Tool):
            def __init__(self):
                super().__init__(
                    name="calculator",
                    description="Perform basic arithmetic operations (add, subtract, multiply, divide)"
                )

            async def execute(self, operation: str, a: float, b: float) -> Any:
                ops = {
                    "add": lambda x, y: x + y,
                    "subtract": lambda x, y: x - y,
                    "multiply": lambda x, y: x * y,
                    "divide": lambda x, y: x / y if y != 0 else "Error: Division by zero"
                }
                op_func = ops.get(operation)
                if op_func:
                    return op_func(a, b)
                return f"Error: Unknown operation {operation}"

        return CalculatorTool()


# Export common tools
def get_default_tools():
    """Get default tools"""
    return [
        TimeTools.get_current_time_tool(),
        CalculatorTools.get_calculator_tool()
    ]
