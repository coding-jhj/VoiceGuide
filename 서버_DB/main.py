import os
import re
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from urllib.parse import quote_plus

app = FastAPI()

def _get_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def _get_db_url() -> str:
    # 1) DATABASE_URL이 있으면 그 값을 그대로 사용
    # 예: postgresql://USER:PASSWORD@HOST:5432/DBNAME?sslmode=require
    direct = os.getenv("DATABASE_URL")
    if direct:
        return direct

    # 2) 없으면 개별 값으로 조립 (Supabase Postgres 직결/로컬 Postgres 모두 가능)
    host = _get_env("PGHOST")
    port = int(os.getenv("PGPORT", "5432"))
    dbname = os.getenv("PGDATABASE", "postgres")
    user = os.getenv("PGUSER", "postgres")
    password = _get_env("PGPASSWORD")
    sslmode = os.getenv("PGSSLMODE", "require")  # Supabase는 보통 require 필요

    return (
        f"postgresql://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/{quote_plus(dbname)}"
        f"?sslmode={quote_plus(sslmode)}"
    )


# ITEMS_TABLE을 startup보다 먼저 선언 — _startup() 내부에서 참조하므로
ITEMS_TABLE = os.getenv("POSTGRES_ITEMS_TABLE", "items")

pool: ConnectionPool | None = None


@app.on_event("startup")
def _startup() -> None:
    global pool
    # Prevent accidental SQL injection via env var misconfiguration.
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", ITEMS_TABLE):
        raise RuntimeError(
            "Invalid POSTGRES_ITEMS_TABLE. Use only letters/numbers/_ and must not start with a number."
        )
    if pool is None:
        pool = ConnectionPool(_get_db_url(), min_size=1, max_size=10, open=True)


@app.on_event("shutdown")
def _shutdown() -> None:
    global pool
    if pool is not None:
        pool.close()
        pool = None


def _pool() -> ConnectionPool:
    if pool is None:
        raise RuntimeError("DB pool is not initialized")
    return pool


@app.get("/health")
def health():
    # DB까지 확인하고 싶으면 아래 주석을 해제하세요.
    # with _pool().connection() as conn:
    #     with conn.cursor() as cur:
    #         cur.execute("select 1 as ok")
    #         cur.fetchone()
    return {"status": "ok"}


@app.get("/")
def read_root():
    return {
        "service": "postgres-fastapi",
        "message": "서버가 정상 작동 중입니다!",
        "endpoints": ["/health", "/items", "/items/{id}"],
    }


class ItemCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    mode: Optional[int] = None


class ItemUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    mode: Optional[int] = None


class DetectRequest(BaseModel):
    mode: int


@app.get("/items")
def list_items(limit: int = 50, offset: int = 0) -> dict[str, Any]:
    limit = max(0, min(limit, 200))
    offset = max(0, offset)
    q = f'SELECT * FROM "{ITEMS_TABLE}" ORDER BY id ASC LIMIT %s OFFSET %s'
    with _pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(q, (limit, offset))
            rows = cur.fetchall()
    return {"data": rows}


@app.get("/items/{item_id}")
def get_item(item_id: int) -> dict[str, Any]:
    q = f'SELECT * FROM "{ITEMS_TABLE}" WHERE id = %s'
    with _pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(q, (item_id,))
            row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"data": row}


@app.post("/items")
def create_item(payload: ItemCreate) -> dict[str, Any]:
    q = f'INSERT INTO "{ITEMS_TABLE}" (name, mode) VALUES (%s, %s) RETURNING *'
    with _pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(q, (payload.name, payload.mode))
            row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=500, detail="Insert failed")
    return {"data": row}


@app.patch("/items/{item_id}")
def update_item(item_id: int, payload: ItemUpdate) -> dict[str, Any]:
    updates = payload.model_dump()
    name = updates.get("name")
    mode = updates.get("mode")
    if name is None and mode is None:
        raise HTTPException(status_code=400, detail="No fields to update")

    q = f"""
    UPDATE "{ITEMS_TABLE}"
       SET name = COALESCE(%s, name),
           mode = COALESCE(%s, mode)
     WHERE id = %s
     RETURNING *
    """
    with _pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(q, (name, mode, item_id))
            row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"data": row}


@app.delete("/items/{item_id}")
def delete_item(item_id: int) -> dict[str, Any]:
    q = f'DELETE FROM "{ITEMS_TABLE}" WHERE id = %s RETURNING *'
    with _pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(q, (item_id,))
            row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"deleted": True, "data": row}


# 기존 예시였던 /detect는 DB 저장 예시로 변경
@app.post("/detect")
def run_detection(payload: DetectRequest) -> dict[str, Any]:
    q = f'INSERT INTO "{ITEMS_TABLE}" (name, mode) VALUES (%s, %s) RETURNING *'
    with _pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(q, ("detection", payload.mode))
            row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=500, detail="Insert failed")
    return {"status": "success", "saved": row}