from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import json
import uuid
from datetime import datetime

from bot import BotEngine

app = FastAPI()

# Serve a pasta static
app.mount("/static", StaticFiles(directory="static"), name="static")

# Agora / abre o HTML
@app.get("/")
def home():
    return FileResponse("static/index.html")

# (Opcional) rota health/check
@app.get("/health")
def health():
    return {"status": "ok"}

# WebSocket do chat
@app.websocket("/ws")
async def ws_chat(ws: WebSocket):
    await ws.accept()

    session_id = str(uuid.uuid4())[:8]
    bot = BotEngine()

    await ws.send_text(json.dumps({
        "sender": "bot",
        "text": bot.start_message(),
        "ts": datetime.now().isoformat(timespec="seconds"),
        "session": session_id
    }))

    try:
        while True:
            data = await ws.receive_text()
            try:
                payload = json.loads(data)
                user_text = payload.get("text", "")
            except:
                user_text = data

            answer = bot.respond(user_text)

            await ws.send_text(json.dumps({
                "sender": "bot",
                "text": answer,
                "ts": datetime.now().isoformat(timespec="seconds"),
                "session": session_id
            }))

    except WebSocketDisconnect:
        return