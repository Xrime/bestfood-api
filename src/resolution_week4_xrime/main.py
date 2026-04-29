from fastapi import FastAPI ,Depends, HTTPException, Header, Request,BackgroundTasks
import secrets
import sqlite3
from pydantic import BaseModel
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded

import os

app = FastAPI()

conn = sqlite3.connect("datas.db")
cursor = conn.cursor()

cursor.execute("""
               CREATE TABLE IF NOT EXISTS food_spots(
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               name TEXT NOT NULL,
               location TEXT NOT NULL,
               rating REAL,
               verified INTEGER DEFAULT 0
               )""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS api_keys(
               key TEXT PRIMARY KEY,
               owner TEXT NOT NULL)
""")
conn.commit()

def create_api_key(owner: str) -> str:
    key = secrets.token_hex(16)
    cursor.execute(
        "INSERT INTO api_keys (key, owner) VALUES (?, ?)",
        (key, owner)
    )
    conn.commit()
    return key

async def verify_api_key(x_api_key: str = Header()):
    cursor.execute("SELECT * FROM api_keys WHERE key = ?", (x_api_key,))
    result = cursor.fetchone()
    if result is None:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return result

@app.get("/secret-data", dependencies=[Depends(verify_api_key)])
async def get_secret_data():
    return {"message": "You have access!"}


class RegisterBody(BaseModel):
    name: str

@app.post("/register")
async def register(body: RegisterBody):
    key = create_api_key(body.name)
    return {"api_key": key, "message":" save this key! You won't be able to see it again"}

def get_api_key(request: Request) -> str:
    return request.headers.get("x-api-key", "unknown")

limiter = Limiter(key_func=get_api_key)
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded. Try again later!"}
    )

class FoodSpotBody(BaseModel):
    name: str
    location: str
    rating: float

@app.post("/food-spots", dependencies=[Depends(verify_api_key)])
@limiter.limit("3/minute")
async def add_spot(request: Request, body: FoodSpotBody, background_tasks: BackgroundTasks, user: str = Depends(verify_api_key)):
    cursor.execute(
        "INSERT INTO food_spots (name, location, rating) VALUES (?, ?, ?)",
        (body.name, body.location, body.rating)
        )
    conn.commit()
    spot_id = cursor.lastrowid
    return {"id": spot_id, "message": f"Spot added successfully by {user}"}




@app.get("/food-spots")
async def get_spots(user: str = Depends(verify_api_key)):
    cursor.execute("SELECT * FROM food_spots")
    rows = cursor.fetchall()
    return [{"id": r[0], "name": r[1], "location": r[2], "rating": r[3], "verified": bool(r[4])} for r in rows]


@app.delete("/food-spots/{spot_id}")
async def delete_spot(spot_id: int, user: str = Depends(verify_api_key)):
    cursor.execute("DELETE FROM food_spots WHERE id = ?", (spot_id,))
    conn.commit()
    return {"message": f"Spot {spot_id} deleted by {user}"}