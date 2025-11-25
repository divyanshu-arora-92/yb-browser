from typing import List, Dict, Any, TypedDict, Optional, Literal

class CoordinatorState(TypedDict):
    ws: Any = None
    browser_manager: Any = None
    conversation_history: List[Any] = []
    last_user_message: str = None
    model_response: Any = None
    tool_call: bool = False
    subgraph_states: List[Any] = []
    url: str = ""
