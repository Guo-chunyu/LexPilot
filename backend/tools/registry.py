"""Tool Registry - unified tool registration, format conversion, and execution."""
from typing import Any, Callable


class ToolDef:
    def __init__(self, name: str, description: str, parameters: dict,
                 handler: Callable | None = None):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.handler = handler

    def to_openai_format(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def execute(self, arguments: dict) -> Any:
        if self.handler is None:
            raise NotImplementedError(f"Tool '{self.name}' has no handler")
        return self.handler(**arguments)


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, ToolDef] = {}

    def register(self, name: str, description: str, parameters: dict,
                 handler: Callable | None = None) -> "ToolRegistry":
        self._tools[name] = ToolDef(name, description, parameters, handler)
        return self

    def list_tools(self) -> list[dict]:
        return [t.to_openai_format() for t in self._tools.values()]

    def execute(self, name: str, arguments: dict) -> Any:
        if name not in self._tools:
            return {"error": f"Unknown tool: {name}"}
        try:
            return self._tools[name].execute(arguments)
        except Exception as e:
            return {"error": str(e)}

    def get_tool_names(self) -> list[str]:
        return list(self._tools.keys())
