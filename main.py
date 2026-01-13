
from fastapi import FastAPI

app = FastAPI(title="API Exemplo", version="1.0.0")

@app.get("/")
def home():
    return {"mensagem": "API no ar"}

@app.get("/soma")
def soma(a: int, b: int):
    return {"a": a, "b": b, "resultado": a + b}


