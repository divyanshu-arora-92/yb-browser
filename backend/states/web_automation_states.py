from typing import List, Dict, Any, TypedDict, Optional, Literal

class WebAutomationState(TypedDict):
    browser_manager: Any
    goal_statement: str = ""
    page: Any = None
    last_screenshot: Any = None
    last_elements: Any = None
    action: Any = None
    action_args: Dict[str, Any] = {}
    action_history: List[Any] = []
    
