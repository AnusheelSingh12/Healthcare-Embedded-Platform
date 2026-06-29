import asyncio
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import models  # noqa: F401
from app.config import ALLOWED_ORIGINS, FRONTEND_DIR, SERIAL_BAUDRATE, SERIAL_TIMEOUT
from app.database import Base, SessionLocal, engine, get_db
from app.services.inventory_service import (
    clear_event_log,
    get_all_items,
    get_category_breakdown,
    get_recent_events,
    get_movement_sessions,
    get_quick_stats,
    get_tool_presence,
    register_serial_event,
    seed_items,
    update_item,
)
from app.services.ports import list_available_ports
from app.services.serial_listener import SerialListener
from app.websocket_manager import WebSocketManager


class ConnectPayload(BaseModel):
    port: str


class UpdateItemPayload(BaseModel):
    new_uid: str | None = None
    name: str | None = None
    category: str | None = None
    status: str | None = None


manager = WebSocketManager()
listener: SerialListener | None = None
main_loop: asyncio.AbstractEventLoop | None = None


def _ensure_event_columns() -> None:
    # Lightweight SQLite-safe migration for older local DB files.
    with engine.begin() as conn:
        rows = conn.execute(text("PRAGMA table_info(movement_events)")).fetchall()
        existing = {str(row[1]) for row in rows}
        if "gauze_count" not in existing:
            conn.execute(text("ALTER TABLE movement_events ADD COLUMN gauze_count INTEGER NOT NULL DEFAULT 0"))
        if "tools_missing" not in existing:
            conn.execute(text("ALTER TABLE movement_events ADD COLUMN tools_missing INTEGER NOT NULL DEFAULT 0"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    global listener, main_loop

    Base.metadata.create_all(bind=engine)
    _ensure_event_columns()

    with SessionLocal() as db:
        seed_items(db)

    main_loop = asyncio.get_running_loop()

    def on_serial_event(serial_payload: dict) -> None:
        if main_loop is None:
            return

        with SessionLocal() as db:
            payload = register_serial_event(db, serial_payload)
            payload["category_breakdown"] = get_category_breakdown(db)

        asyncio.run_coroutine_threadsafe(manager.broadcast_json(payload), main_loop)

    def on_error(message: str) -> None:
        if main_loop is None:
            return
        payload = {"event": "error", "message": message}
        asyncio.run_coroutine_threadsafe(manager.broadcast_json(payload), main_loop)

    listener = SerialListener(
        on_event=on_serial_event,
        on_error=on_error,
        baudrate=SERIAL_BAUDRATE,
        timeout=SERIAL_TIMEOUT,
    )

    yield

    if listener and listener.is_running:
        listener.stop()


app = FastAPI(title="RFID Surgical Inventory", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/")
def serve_dashboard():
    index_path = FRONTEND_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Dashboard file not found")
    return FileResponse(index_path)


@app.get("/history")
def serve_history():
    history_path = FRONTEND_DIR / "history.html"
    if not history_path.exists():
        raise HTTPException(status_code=404, detail="History page not found")
    return FileResponse(history_path)


@app.get("/api/ports")
def get_ports():
    return {"ports": list_available_ports()}


@app.post("/api/connect")
def connect_port(payload: ConnectPayload):
    if listener is None:
        raise HTTPException(status_code=500, detail="Listener unavailable")

    available = {entry["device"] for entry in list_available_ports()}
    if payload.port not in available:
        raise HTTPException(status_code=400, detail="Selected port is not available")

    if listener.is_running:
        listener.stop()

    try:
        listener.start(payload.port)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to start listener: {exc}") from exc

    return {"connected": True, "port": payload.port}


@app.post("/api/disconnect")
def disconnect_port():
    if listener and listener.is_running:
        listener.stop()
    return {"connected": False}


@app.get("/api/status")
def listener_status():
    if listener is None:
        return {"connected": False, "port": None}
    return {"connected": listener.is_running, "port": listener.active_port}


@app.get("/api/stats")
def quick_stats(db: Session = Depends(get_db)):
    return get_quick_stats(db)


@app.get("/api/categories")
def category_breakdown(db: Session = Depends(get_db)):
    return {"categories": get_category_breakdown(db)}


@app.get("/api/items")
def list_items(db: Session = Depends(get_db)):
    return {"items": get_all_items(db)}


@app.put("/api/items/{uid}")
def edit_item(uid: str, payload: UpdateItemPayload, db: Session = Depends(get_db)):
    try:
        updated = update_item(
            db,
            uid,
            new_uid=payload.new_uid,
            name=payload.name,
            category=payload.category,
            status=payload.status,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if updated is None:
        raise HTTPException(status_code=404, detail="Item not found")

    return {"item": updated}


@app.get("/api/movement-sessions")
def movement_sessions(limit: int = 200, db: Session = Depends(get_db)):
    safe_limit = max(1, min(limit, 1000))
    return {"sessions": get_movement_sessions(db, safe_limit)}


@app.get("/api/events")
def event_log(limit: int = 300, db: Session = Depends(get_db)):
    safe_limit = max(1, min(limit, 1000))
    return {"events": get_recent_events(db, safe_limit)}


@app.post("/api/events/clear")
def clear_events(db: Session = Depends(get_db)):
    clear_event_log(db)
    return {"cleared": True}


@app.get("/api/tools/presence")
def tool_presence(db: Session = Depends(get_db)):
    return get_tool_presence(db)


@app.websocket("/ws/rfid")
async def rfid_ws(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        await websocket.send_json({"event": "listener_status", "connected": listener.is_running if listener else False, "port": listener.active_port if listener else None})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)
