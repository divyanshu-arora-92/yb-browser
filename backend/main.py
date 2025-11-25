# uvicorn backend.main:app --host 0.0.0.0 --port 8000

from contextlib import asynccontextmanager
from typing import Set, Any
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from backend.browser.manager import BrowserManager
from backend.states.coordinator_states import CoordinatorState
from backend.agents.coordinator_agent import coordinator_agent_graph

# --- Lifespan / app startup-shutdown using asynccontextmanager ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Start the persistent Playwright browser once and store it on app.state.
    Stop it cleanly on shutdown.
    """
    app.state.browser_manager = BrowserManager()
    print("LIFESPAN: starting browser manager...")
    await app.state.browser_manager.start()
    try:
        yield
    finally:
        print("LIFESPAN: stopping browser manager...")
        await app.state.browser_manager.stop()

app = FastAPI(lifespan=lifespan)

# Keep track of active websockets
active_connections: Set[WebSocket] = set()
ui_states = {}

def get_ui_state(uid, message, ws):
    if uid not in ui_states:
        ui_state = CoordinatorState()
        ui_state['ws'] = ws
        ui_state['browser_manager'] = ws.app.state.browser_manager
        ui_state['conversation_history'] = []
        ui_state['tool_call'] = False
        ui_states[uid] = ui_state
    else:
        ui_state = ui_states[uid]
    ui_state['last_user_message'] = message
    return ui_states[uid]

@app.get("/", response_class=HTMLResponse)
def index():
    return "<h3>Playwright WebSocket server is running. Connect to /ws</h3>"

# --- WebSocket endpoint ---
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    active_connections.add(ws)
    print("Client connected, total:", len(active_connections))

    bm: BrowserManager = None
    # access browser manager from app.state; fallback if not present
    try:
        bm = ws.app.state.browser_manager
    except Exception:
        # shouldn't happen if lifespan ran
        await ws.send_json({"error": "browser manager not available"})
        await ws.close()
        return

    try:
        while True:
            # Expect JSON messages like: {"action":"goto","url":"https://example.com","page_index":0}
            data = await ws.receive_text()
            try:
                payload = json.loads(data)
            except json.JSONDecodeError:
                await ws.send_json({"error": "invalid json"})
                continue
            
            uid = payload.get("uid")
            message = payload["text"]
            ui_state = get_ui_state(uid, message, ws)
            await coordinator_agent_graph.ainvoke(ui_state)

            # else:
            #     await ws.send_json({"error": f"unknown action '{action}'"})

    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as e:
        print("Websocket error:", e)
        # try to notify client before closing
        try:
            await ws.send_json({"error": str(e)})
        except Exception:
            pass
    finally:
        active_connections.discard(ws)
        try:
            await ws.close()
        except Exception:
            pass
        print("Connection closed, total:", len(active_connections))
