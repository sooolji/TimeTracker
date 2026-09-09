from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from server import ai, excel_export
from server.db import connect, init_db, row_to_dict, utc_now

load_dotenv()

AUTHOR = os.getenv("REPORT_AUTHOR", "Jonathan")
TEMPLATE = os.getenv("TEMPLATE_NAME", "yyyy-mm-dd nombre.xlsx")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="TimeTracker", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class NoteIn(BaseModel):
    content: str = Field(min_length=1)
    day: str


class TaskIn(BaseModel):
    title: str = Field(min_length=1)
    url: str | None = None
    day: str
    status: Literal["todo", "doing", "done"] = "todo"


class TaskPatch(BaseModel):
    title: str | None = None
    url: str | None = None
    status: Literal["todo", "doing", "done"] | None = None
    day: str | None = None


class Block(BaseModel):
    start: str
    end: str
    title: str
    description: str = ""


class PreviewIn(BaseModel):
    date: str
    start_time: str = "13:00"
    end_time: str = "20:00"
    use_ai: bool = True


class ExportIn(BaseModel):
    date: str
    start_time: str
    end_time: str
    blocks: list[Block]
    overwrite: bool = False


@app.get("/api/config")
def get_config():
    return {
        "author": AUTHOR,
        "ai_available": ai.ai_configured(),
        "ai_provider": ai.ai_provider(),
        "default_start": "13:00",
        "default_end": "20:00",
    }


@app.get("/api/day")
def get_day(date: str):
    with connect() as conn:
        notes = [
            row_to_dict(r)
            for r in conn.execute(
                "SELECT * FROM notes WHERE day = ? ORDER BY created_at ASC, id ASC",
                (date,),
            )
        ]
        tasks = [
            row_to_dict(r)
            for r in conn.execute(
                """
                SELECT * FROM tasks
                WHERE day = ? OR status != 'done'
                ORDER BY
                    CASE status WHEN 'doing' THEN 0 WHEN 'todo' THEN 1 ELSE 2 END,
                    created_at ASC,
                    id ASC
                """,
                (date,),
            )
        ]
        reports = [
            row_to_dict(r)
            for r in conn.execute(
                "SELECT * FROM reports WHERE date = ? ORDER BY generated_at DESC",
                (date,),
            )
        ]
    dest = excel_export.destination_path(date, AUTHOR)
    return {
        "date": date,
        "notes": notes,
        "tasks": tasks,
        "reports": reports,
        "xlsx_exists": dest.exists(),
        "xlsx_name": dest.name,
    }


@app.post("/api/notes")
def create_note(payload: NoteIn):
    content = payload.content.strip()
    if not content:
        raise HTTPException(400, "La nota está vacía.")
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO notes (content, day, created_at) VALUES (?, ?, ?)",
            (content, payload.day, utc_now()),
        )
        row = conn.execute("SELECT * FROM notes WHERE id = ?", (cur.lastrowid,)).fetchone()
    return row_to_dict(row)


@app.delete("/api/notes/{note_id}")
def delete_note(note_id: int):
    with connect() as conn:
        cur = conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        if cur.rowcount == 0:
            raise HTTPException(404, "Nota no encontrada.")
    return {"ok": True}


@app.post("/api/tasks")
def create_task(payload: TaskIn):
    now = utc_now()
    completed = now if payload.status == "done" else None
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO tasks (title, url, status, day, created_at, completed_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                payload.title.strip(),
                (payload.url or "").strip() or None,
                payload.status,
                payload.day,
                now,
                completed,
            ),
        )
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (cur.lastrowid,)).fetchone()
    return row_to_dict(row)


@app.patch("/api/tasks/{task_id}")
def patch_task(task_id: int, payload: TaskPatch):
    with connect() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Tarea no encontrada.")
        data = dict(row)
        if payload.title is not None:
            data["title"] = payload.title.strip()
        if payload.url is not None:
            data["url"] = payload.url.strip() or None
        if payload.day is not None:
            data["day"] = payload.day
        if payload.status is not None:
            data["status"] = payload.status
            if payload.status == "done" and not data.get("completed_at"):
                data["completed_at"] = utc_now()
            if payload.status != "done":
                data["completed_at"] = None
        conn.execute(
            """
            UPDATE tasks
            SET title = ?, url = ?, status = ?, day = ?, completed_at = ?
            WHERE id = ?
            """,
            (
                data["title"],
                data["url"],
                data["status"],
                data["day"],
                data["completed_at"],
                task_id,
            ),
        )
        updated = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return row_to_dict(updated)


@app.delete("/api/tasks/{task_id}")
def delete_task(task_id: int):
    with connect() as conn:
        cur = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        if cur.rowcount == 0:
            raise HTTPException(404, "Tarea no encontrada.")
    return {"ok": True}


@app.post("/api/reports/preview")
async def preview_report(payload: PreviewIn):
    with connect() as conn:
        notes = [
            row_to_dict(r)
            for r in conn.execute(
                "SELECT * FROM notes WHERE day = ? ORDER BY created_at ASC",
                (payload.date,),
            )
        ]
        done_tasks = [
            row_to_dict(r)
            for r in conn.execute(
                """
                SELECT * FROM tasks
                WHERE status = 'done' AND day = ?
                ORDER BY completed_at ASC, id ASC
                """,
                (payload.date,),
            )
        ]

    source = "heuristic"
    warning = None
    blocks = None
    if payload.use_ai and ai.ai_configured():
        try:
            blocks = await ai.generate_with_ai(
                start=payload.start_time,
                end=payload.end_time,
                notes=notes,
                done_tasks=done_tasks,
            )
            source = "ai"
        except Exception as exc:
            warning = f"La IA falló ({exc}). Se usó el reparto automático."
    if blocks is None:
        try:
            blocks = ai.heuristic_blocks(
                start=payload.start_time,
                end=payload.end_time,
                notes=notes,
                done_tasks=done_tasks,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    dest = excel_export.destination_path(payload.date, AUTHOR)
    return {
        "source": source,
        "warning": warning,
        "blocks": blocks,
        "xlsx_exists": dest.exists(),
        "xlsx_name": dest.name,
    }


@app.post("/api/reports/export")
def export_report(payload: ExportIn):
    blocks = [b.model_dump() for b in payload.blocks]
    dest = excel_export.destination_path(payload.date, AUTHOR)
    try:
        path = excel_export.write_report(
            day=payload.date,
            author=AUTHOR,
            blocks=blocks,
            overwrite=payload.overwrite,
            template=TEMPLATE,
        )
    except FileExistsError:
        raise HTTPException(
            status_code=409,
            detail={
                "message": f"Ya existe {dest.name}. Confirma para sobrescribir.",
                "xlsx_name": dest.name,
            },
        )
    except excel_export.ExportError as exc:
        raise HTTPException(400, str(exc)) from exc

    with connect() as conn:
        conn.execute(
            """
            INSERT INTO reports (date, start_time, end_time, blocks, xlsx_path, generated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                payload.date,
                payload.start_time,
                payload.end_time,
                json.dumps(blocks, ensure_ascii=False),
                str(path),
                utc_now(),
            ),
        )
    return {
        "ok": True,
        "xlsx_path": str(path),
        "xlsx_name": path.name,
    }
