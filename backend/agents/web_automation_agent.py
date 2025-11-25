import asyncio
import xml.etree.ElementTree as ET
from langgraph.graph import StateGraph, END
from backend.states.web_automation_states import WebAutomationState
from backend.model_interactions.web_automation_model import call_gemini


async def take_snapshot(state: WebAutomationState) -> WebAutomationState:
    image_bytes, xml_data = await state["browser_manager"].take_snapshot(state["page"])
    state["last_screenshot"] = image_bytes
    state["last_elements"] = xml_data
    return state

async def model_decision(state: WebAutomationState) -> WebAutomationState:
    response = call_gemini(goal_statement=state['goal_statement'], history=state['action_history'], 
                           image_bytes=state["last_screenshot"], xml_data=state["last_elements"])
    
    summary, function_name, function_params = None, None, None
    for _part in response.parts:
        if _part.text:
            summary = _part.text.strip()
        if _part.function_call:
            function_name = _part.function_call.name
            function_params = _part.function_call.args
    
    if summary is not None:
        state["action_history"].append(summary)
    
    state["action"] = function_name
    state["action_args"] = function_params
    return state

async def execute_action(state: WebAutomationState) -> WebAutomationState:
    def extract_cordinates(xml_data, element_id):
        root = ET.fromstring(xml_data)
        target_element = root.find(f".//element[@index='{element_id}']")

        center_node = target_element.find('center')
        x = float(center_node.find('x').text)
        y = float(center_node.find('y').text)
        return x, y

    tool_name = state["action"]
    tool_params = state["action_args"]
    page = state["page"]
    session = state["browser_manager"]
    xml_data = state["last_elements"]

    if tool_name == "goto":
        await session.goto(page, tool_params["url"])
    elif tool_name == "click":
        x, y = extract_cordinates(xml_data, tool_params["element_id"])
        await session.action_click(page, x, y)
    elif tool_name == "type_text":
        x, y = extract_cordinates(xml_data, tool_params["element_id"])
        await session.action_typetext(page, x, y, tool_params["text"])
    elif tool_name == "scroll_page":
        direction = tool_params["direction"]
        await session.action_scroll(page=page, direction=direction)
    elif tool_name == "scroll_element":
        direction = tool_params["direction"]
        x, y = extract_cordinates(xml_data, tool_params["element_id"])
        await session.action_scroll(page=page, direction=direction, whole_page=False, x=x, y=y)
    elif tool_name == "back":
        await session.back(page=page)
    elif tool_name == "wait":
        await asyncio.sleep(3)

    return state

def decide_next_step(state: WebAutomationState) -> str:
    action = state["action"]
    if action in ["done", "stuck", "wait_for_input", "wait_for_action"]:
        return END
    else:
        return "execute_action"


graph = StateGraph(WebAutomationState)

graph.add_node("take_snapshot", take_snapshot)
graph.add_node("model_decision", model_decision)
graph.add_node("execute_action", execute_action)

# Entry
graph.set_entry_point("take_snapshot")

# Edges
graph.add_edge("take_snapshot", "model_decision")

# Branching: text or tool call
graph.add_conditional_edges(
    "model_decision",      # The node the decision originates from
    decide_next_step,      # The function that routes the flow
    {                      # Mapping of function output (keys) to next node/END (values)
        "execute_action": "execute_action",
        END: END           # 'done' and 'awaiting' map to END
    }
)
graph.add_edge("execute_action", "take_snapshot")

web_automation_agent_graph = graph.compile()
