import asyncio
from langgraph.graph import StateGraph, END
from google.genai import types 
import json
from backend.model_interactions.coordinator_model import call_gemini
from backend.states.coordinator_states import CoordinatorState
from backend.states.web_automation_states import WebAutomationState
from backend.agents.web_automation_agent import web_automation_agent_graph

async def call_gemini_model(state: CoordinatorState):
    state["tool_call"] = False
    if state["last_user_message"] is None:
        response = call_gemini(conversation_history = state["conversation_history"])
    else:
        pages = await state['browser_manager'].get_page_summaries()
        user_content_with_json = types.Content(
        role="user",
        parts=[
            types.Part.from_text(text=f"{state['last_user_message']}\n\n PAGE DATA IN JSON"),
            types.Part.from_text(text=f"```json\n{json.dumps(pages)}\n```")
        ]
        )

        response = call_gemini(input_content=user_content_with_json,
                               conversation_history = state["conversation_history"])
        
        conversation_history = state["conversation_history"]
        conversation_history.append(types.Content(role="user", parts=[types.Part.from_text(text=state["last_user_message"])]))

        for _part in response.parts:
            if _part.function_call:
                state["tool_call"] = True
                break
        
        state["conversation_history"] = conversation_history
        state["last_user_message"] = None
    
    state["model_response"] = response
    return state


async def process_model_output(state: CoordinatorState):
    # send to Streamlit UI
    state["conversation_history"].append(types.Content(role="model", parts=state["model_response"].parts))
    
    response = []
    for _part in state["model_response"].parts:
        if _part.text:
            response.append({
                "role": "model",
                "text": _part.text
            })
        else:
            response.append({
                "role": "model",
                "function_call": {
                    "name": _part.function_call.name,
                    "args": _part.function_call.args
                }
            })
    await state["ws"].send_json(response)

    # GRAPH WILL STOP → waiting for next user message
    return state


async def handle_tool_call(state: CoordinatorState):
    def get_web_interaction_state(goal, page):
        _state = WebAutomationState()
        _state["browser_manager"] = state["browser_manager"]
        _state["goal_statement"] = goal
        _state["page"] = page
        _state["action_history"] = []
        _state["action"] = None
        # _state["url"] = url
        return _state

    # Build initial subgraph states
    state["subgraph_states"] = []
    for _part in state['model_response'].parts:
        if _part.function_call:
            if "page_index" in _part.function_call.args:
                page = state["browser_manager"].context.pages[_part.function_call.args["page_index"]]
                goal_statement = f"{_part.function_call.args['goal']}"
            else:
                page = await state["browser_manager"].context.new_page()
                goal_statement = f"{_part.function_call.args['goal']} WEBSITE - {_part.function_call.args['url']}"
            _state = get_web_interaction_state(goal=goal_statement, page=page)
            state["subgraph_states"].append(_state)

    # Run all subgraphs and CAPTURE updated states
    subgraph_tasks = [
        web_automation_agent_graph.ainvoke(_state, {"recursion_limit": 80})
        for _state in state["subgraph_states"]
    ]

    updated_states = await asyncio.gather(*subgraph_tasks)

    # Replace with updated versions
    state["subgraph_states"] = updated_states

    return state

    
async def post_tool_calls(state: CoordinatorState):
    conversation_history = state["conversation_history"]
    # message will come from other sources - fucntion call responses
    for _web_interaction_state in state["subgraph_states"]:
        if _web_interaction_state["action"] == "done":
            response_dict = {"result": {"status": "done", "output": _web_interaction_state["action_args"]["output"]}}
        elif _web_interaction_state["action"] == "wait_for_input":
            response_dict = {"result": {"status": "awaiting_input", "output": str(_web_interaction_state["action_args"]["information_required"])}}
        elif _web_interaction_state["action"] == "wait_for_action":
            response_dict = {"result": {"status": "awaiting_user_action", "output": _web_interaction_state["action_args"]["action_required"]}}

        conversation_history.append(types.Content(role="user", parts=[types.Part.from_function_response(name="web_interaction", response=response_dict)]))



graph = StateGraph(CoordinatorState)

graph.add_node("call_gemini_model", call_gemini_model)
graph.add_node("process_model_output", process_model_output)
graph.add_node("handle_tool_call", handle_tool_call)
graph.add_node("post_tool_calls", post_tool_calls)

# Entry
graph.set_entry_point("call_gemini_model")

# Edges
graph.add_edge("call_gemini_model", "process_model_output")

# Branching: text or tool call
graph.add_conditional_edges(
    "process_model_output",
    lambda state: "handle_tool_call" if state["tool_call"] else "end", 
    {
        "handle_tool_call": "handle_tool_call", 
        "end": END
    }
    )
graph.add_edge("handle_tool_call", "post_tool_calls")
graph.add_edge("post_tool_calls", "call_gemini_model")

coordinator_agent_graph = graph.compile()
