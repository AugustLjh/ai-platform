RESPONSE_TYPE_UNSPECIFIED = 0
RESPONSE_TYPE_CONTENT = 1
RESPONSE_TYPE_THINKING = 2
RESPONSE_TYPE_TOOL_CALL = 3
RESPONSE_TYPE_COMPLETE = 4
RESPONSE_TYPE_ERROR = 5


def map_agent_response_type(agent_type: str) -> int:
    mapping = {
        "content": RESPONSE_TYPE_CONTENT,
        "thinking": RESPONSE_TYPE_THINKING,
        "tool_call": RESPONSE_TYPE_TOOL_CALL,
        "complete": RESPONSE_TYPE_COMPLETE,
        "error": RESPONSE_TYPE_ERROR,
    }
    return mapping.get(agent_type, RESPONSE_TYPE_CONTENT)
