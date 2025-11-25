import json
import os
from typing import List, Dict, Any, Optional, Tuple
from google import genai
from google.genai import types # Import the types module
from google.genai.errors import APIError # Import for specific error handling

tool_declarations = [
        {
            "name": "goto",
            "description": "Navigates to a specific URL.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "url": {
                        "type": "STRING",
                        "description": "url for automation, it can be existing page url or new url which tool will browse to"
                    },
                },
                "required": ["url"],
            },
        },
        {
            "name": "click",
            "description": "Clicks on a specific interactive element (e.g., a button, link, or tab).",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "element_id": {
                        "type": "INTEGER",
                        "description": "The unique integer ID of the element to be clicked, corresponding to the ID found in the provided element list XML."
                    },
                },
                "required": ["element_id"],
            },
        },
        {
            "name": "type_text",
            "description": "Types the specified text into an input field or text area.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "element_id": {
                        "type": "INTEGER",
                        "description": "The unique integer ID of the element to be clicked, corresponding to the ID found in the provided element list XML."
                    },
                    "text": {
                        "type": "STRING",
                        "description": "The string content to be entered into the element."
                    },
                },
                "required": ["element_id", "text"],
            },
        },
        {
            "name": "scroll_page",
            "description": "Scrolls the current web page up or down. Use this to reveal content that is initially hidden.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "direction": {
                        "type": "STRING",
                        "enum": ["up", "down", "left", "right"],
                        "description": "direction of the scroll."
                    },
                },
                "required": ["direction"],
            },
        },
        {
            "name": "scroll_element",
            "description": "Scrolls a specific, container-like element (e.g., a modal or sidebar) down to reveal its contained content.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "element_id": {
                        "type": "INTEGER",
                        "description": "The unique integer ID of the element to be clicked, corresponding to the ID found in the provided element list XML."
                    },
                    "direction": {
                        "type": "STRING",
                        "enum": ["up", "down", "left", "right"],
                        "description": "direction of the scroll."
                    },
                },
                "required": ["element_id", "direction"],
            },
        },
        {
            "name": "done",
            "description": "Signals that the goal described by the user has been successfully achieved, and no further actions are necessary.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "output": {
                        "type": "STRING",
                        "description": "a structured representation (e.g., JSON, list, or detailed string) of the information requested."
                    },
                },
                "required": ["output"],
            },
        },
        {
            "name": "wait",
            "description": "Wait for page to load. Use this when content is expected to load before the next interaction.",
            "parameters": {
                "type": "OBJECT",
                "properties": {},
                "required": [],
            },
        },
        {
            "name": "stuck",
            "description": "Signals that the automation process is blocked, lost, or the available inputs (screenshot/XML) are insufficient or invalid to continue working toward the goal. This should be used when the model cannot proceed.",
            "parameters": {
                "type": "OBJECT",
                "properties": {},
                "required": [],
            },
        },
        {
            "name": "wait_for_action",
            "description": "Execution requires to make a decision or action only the human user can perform.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "action_required": {
                        "type": "STRING",
                        "description": "description of action needed."
                    },
                },
                "required": ["action_required"],
            },
        },
        {
            "name": "wait_for_input",
            "description": "Get any missing or required information which is hindering from the achieving goal.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "information_required": {
                        "type": "ARRAY",
                        "items": {"type": "string"},
                        "description": "list of fields required to proceed forward."
                    },
                },
                "required": ["information_required"],
            },
        },
    ]

def generate_system_prompt(goal_statement):
    return f"""
### 1. Persona and Goal (P & T)
You are an expert **Web Automation Agent** tasked with navigating and interacting with a single web browser tab. 
Your sole function is to analyze the current state and select the single, best tool to take the next action toward the {goal_statement}.

### 2. Context and State (C)
You are in an iterative agent loop. For every turn, you are provided with:
1.  **Screenshot:** A visual reference of the current page (if current page exists).
2.  **WebElements:** A structured list of all interactive elements, containing their unique integer `element_id` (if current page exists).
3.  **History:** A summary of past actions taken.

### 3. Constraints and Logic
* **Action Mandate:** You **MUST** select exactly one tool call.
* **Summary Mandate:** You **MUST** provide a concise natural language action_summary (2-10 words) describing the action taken before the function call.
* **Element IDs:** All `click`, `type_text`, and `scroll_element` calls **MUST** use a valid `element_id` from the provided `WebElements` list.
* **Goal Completion:**
    * Use `done` **ONLY** when the goal is definitively and visibly achieved (e.g., search results are displayed, final form is submitted).
    * Use `stuck` if you are blocked, lost, or a necessary element is missing despite scrolling.
* **Navigation:** Use `scroll_page` if the target element is likely off-screen. Use `back` only if the goal requires returning to a previous page state.
"""

def call_gemini(goal_statement: str, history: list[str] = [], image_bytes: bytes = None, xml_data: str = "") -> Tuple[str, List[Dict[str, Any]]]:
    client = genai.Client(api_key=os.environ.get("GENAI_API_KEY"))
    model = "gemini-flash-lite-latest" 

    generate_content_config = types.GenerateContentConfig(
        temperature=0,
        thinking_config = types.ThinkingConfig(thinking_budget=-1,),
        tools=[types.Tool(function_declarations=tool_declarations)],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        system_instruction=[types.Part.from_text(text=generate_system_prompt(goal_statement))],
    )

    user_parts = []
    if history:
        user_parts.append(types.Part.from_text(text="PAST ACTIONS:\n"+"\n".join(history)))
    else:
        user_parts.append(types.Part.from_text(text="No history, start of action."))
    if image_bytes:
        user_parts.append(types.Part.from_bytes(data=image_bytes, mime_type='image/png'))
    if xml_data:
        user_parts.append(types.Part.from_text(text="XML Data:\n"+xml_data))

    contents = [types.Content(role="user", parts=user_parts)]

    try:
        response = client.models.generate_content(
                model=model,
                contents=contents,
                config=generate_content_config
            )
    except APIError as e:
        raise
    except Exception as e:
        raise
    try:
        return response.candidates[0].content
    except Exception as e:
        print(response)
