"""Upload API — POST /api/upload-csv."""
from __future__ import annotations

import csv
import io
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from src.config.settings import get_settings
from src.db.session import _get_engine
from src.db.models import UploadedData

router = APIRouter()


class UploadResponse(BaseModel):
    success: bool
    upload_id: str
    original_filename: str
    table_name: str
    row_count: int
    columns: list[str]
    message: str | None = None


_MAX_ROWS = 500_000
_MAX_BYTES = 200 * 1024 * 1024  # 200 MB
_ALLOWED_EXT = ".csv"
_CHUNK = 5_000


def _safe_table_name(filename: str) -> str:
    stem = re.sub(r"[^a-zA-Z0-9_]", "_", os.path.splitext(filename)[0].lower())
    stem = re.sub(r"_+", "_", stem).strip("_") or "csv"
    suffix = uuid.uuid4().hex[:8]
    return f"uploaded_{stem}_{suffix}"


@router.post("/upload-csv", response_model=UploadResponse)
async def upload_csv(file: UploadFile = File(...)) -> dict[str, Any]:
    if not file.filename or not file.filename.lower().endswith(_ALLOWED_EXT):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted.")

    content = await file.read()
    if len(content) > _MAX_BYTES:
        raise HTTPException(status_code=400, detail="File exceeds 200 MB limit.")

    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File is not valid UTF-8 text.")

    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        raise HTTPException(status_code=400, detail="CSV is empty.")

    header = [str(h).strip() for h in header if str(h).strip()]
    if not header:
        raise HTTPException(status_code=400, detail="CSV has no visible column headers.")

    # Peek at first row for type inference
    sample_rows: list[list[str]] = []
    for idx, row in enumerate(reader, start=1):
        if idx > _CHUNK:
            break
        sample_rows.append([str(v) for v in row])
    total_rows = idx  # total data rows from the iterator in this chunk pass
    # Note: for exact total_rows we'd need a second pass; use length(reader) first pass in prod.

    # Save full content and re-parse for insert
    reader = csv.reader(io.StringIO(text))
    next(reader)  # skip header again
    rows: list[list[str]] = []
    for row in reader:
        rows.append([str(v) for v in row])
    total_rows = len(rows)

    if total_rows > _MAX_ROWS:
        raise HTTPException(status_code=400, detail="CSV exceeds 500,000 rows.")

    table_name = _safe_table_name(file.filename)
    cols_sql = ", ".join(f'"{h}" TEXT' for h in header)
    create_sql = f'CREATE TABLE "{table_name}" ({cols_sql})'

    placeholders = ", ".join(["?"] * len(header))
    insert_sql = f'INSERT INTO "{table_name}" VALUES ({placeholders})'

    engine = _get_engine()
    conn = engine.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(create_sql)
        cur.executemany(insert_sql, rows)
        conn.commit()
    finally:
        try:
            conn.close()
        except Exception:
            pass

    upload_id = str(uuid.uuid4())
    with _get_engine().connect() as conn:
        from sqlalchemy import text
        conn.execute(
            text(
                "INSERT INTO uploaded_data (id, original_filename, stored_filename, mime_type, size_bytes, row_count, columns_json, table_name, uploaded_at) VALUES (:id,:original,:stored,:mime,:size,:rows,:cols,:tbl,:at)"
            ),
            {
                "id": upload_id,
                "original": file.filename,
                "stored": table_name,
                "mime": file.content_type,
                "size": len(content),
                "rows": total_rows,
                "cols": {"columns": header},
                "tbl": table_name,
                "at": datetime.now(timezone.utc),
            },
        )
        conn.commit()

    return UploadResponse(
        success=True,
        upload_id=upload_id,
        original_filename=file.filename or "upload.csv",
        table_name=table_name,
        row_count=total_rows,
        columns=header,
        message=f"Imported {total_rows} rows into table {table_name}.",
    ).dict()


@router.get("/uploads")
def list_uploads() -> dict[str, Any]:
    with _get_engine().connect() as conn:
        from sqlalchemy import text
        rows = conn.execute(text("SELECT id, original_filename, table_name, row_count, uploaded_at FROM uploaded_data ORDER BY uploaded_at DESC LIMIT 50")).fetchall()
    items = [
        {
            "id": r[0],
            "original_filename": r[1],
            "table_name": r[2],
            "row_count": r[3],
            "uploaded_at": r[4].isoformat() if r[4] else None,
        }
        for r in rows
    ]
    return {"uploads": items}
