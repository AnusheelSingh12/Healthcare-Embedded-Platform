from fastapi import WebSocket


class WebSocketManager:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._clients.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self._clients.discard(websocket)

    async def broadcast_json(self, payload: dict) -> None:
        stale_clients: list[WebSocket] = []
        for client in self._clients:
            try:
                await client.send_json(payload)
            except Exception:
                stale_clients.append(client)

        for client in stale_clients:
            self.disconnect(client)
