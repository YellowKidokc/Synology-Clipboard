import json
import sqlite3
from pathlib import Path
from typing import Any


class Store:
    def __init__(self, database: str | Path):
        self.database = str(database)
        Path(self.database).parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def initialize(self) -> None:
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS clips (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    content_type TEXT NOT NULL DEFAULT 'text',
                    title TEXT NOT NULL DEFAULT '',
                    source_app TEXT NOT NULL DEFAULT '',
                    source_window TEXT NOT NULL DEFAULT '',
                    tags TEXT NOT NULL DEFAULT '[]',
                    pinned INTEGER NOT NULL DEFAULT 0,
                    archived INTEGER NOT NULL DEFAULT 0,
                    sensitive INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                );
                CREATE INDEX IF NOT EXISTS clips_created_at ON clips(created_at DESC);
                CREATE TABLE IF NOT EXISTS prompts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    template TEXT NOT NULL,
                    tags TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                );
                """
            )

    @staticmethod
    def _item(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["tags"] = json.loads(item.get("tags", "[]"))
        for key in ("pinned", "archived", "sensitive"):
            if key in item:
                item[key] = bool(item[key])
        return item

    def add_clip(self, payload: dict[str, Any]) -> dict[str, Any]:
        content = str(payload.get("content", "")).strip()
        if not content:
            raise ValueError("content is required")
        tags = payload.get("tags", [])
        if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
            raise ValueError("tags must be a list of strings")
        values = (
            content, str(payload.get("content_type", "text")), str(payload.get("title", "")),
            str(payload.get("source_app", "")), str(payload.get("source_window", "")),
            json.dumps(tags), bool(payload.get("pinned")), bool(payload.get("archived")),
            bool(payload.get("sensitive")),
        )
        with self.connect() as db:
            cursor = db.execute(
                """INSERT INTO clips
                (content, content_type, title, source_app, source_window, tags, pinned, archived, sensitive)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""", values
            )
            row = db.execute("SELECT * FROM clips WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return self._item(row)

    def clips(self, query: str = "", archived: bool = False, limit: int = 100) -> list[dict[str, Any]]:
        where, values = ["archived = ?"], [int(archived)]
        if query:
            where.append("(content LIKE ? OR title LIKE ? OR tags LIKE ? OR source_app LIKE ?)")
            term = f"%{query}%"
            values.extend([term] * 4)
        values.append(min(max(limit, 1), 500))
        with self.connect() as db:
            rows = db.execute(
                f"SELECT * FROM clips WHERE {' AND '.join(where)} ORDER BY pinned DESC, created_at DESC LIMIT ?",
                values,
            ).fetchall()
        return [self._item(row) for row in rows]

    def update_clip(self, clip_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
        allowed = {"title", "tags", "pinned", "archived", "sensitive"}
        changes, values = [], []
        for key, value in payload.items():
            if key not in allowed:
                continue
            if key == "tags":
                if not isinstance(value, list) or not all(isinstance(tag, str) for tag in value):
                    raise ValueError("tags must be a list of strings")
                value = json.dumps(value)
            if key in {"pinned", "archived", "sensitive"}:
                value = int(bool(value))
            changes.append(f"{key} = ?")
            values.append(value)
        if not changes:
            raise ValueError("no supported fields supplied")
        values.append(clip_id)
        with self.connect() as db:
            db.execute(f"UPDATE clips SET {', '.join(changes)} WHERE id = ?", values)
            row = db.execute("SELECT * FROM clips WHERE id = ?", (clip_id,)).fetchone()
        return self._item(row) if row else None

    def delete_clip(self, clip_id: int) -> bool:
        with self.connect() as db:
            return db.execute("DELETE FROM clips WHERE id = ?", (clip_id,)).rowcount > 0

    def prompts(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM prompts ORDER BY created_at DESC").fetchall()
        return [self._item(row) for row in rows]

    def add_prompt(self, payload: dict[str, Any]) -> dict[str, Any]:
        name, template = str(payload.get("name", "")).strip(), str(payload.get("template", "")).strip()
        tags = payload.get("tags", [])
        if not name or not template:
            raise ValueError("name and template are required")
        if not isinstance(tags, list):
            raise ValueError("tags must be a list")
        with self.connect() as db:
            cursor = db.execute("INSERT INTO prompts(name, template, tags) VALUES (?, ?, ?)", (name, template, json.dumps(tags)))
            row = db.execute("SELECT * FROM prompts WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return self._item(row)

    def combine(self, ids: list[int], mode: str) -> str:
        if not ids:
            raise ValueError("ids must not be empty")
        placeholders = ",".join("?" for _ in ids)
        with self.connect() as db:
            rows = db.execute(f"SELECT id, content FROM clips WHERE id IN ({placeholders})", ids).fetchall()
        content = {row["id"]: row["content"] for row in rows}
        parts = [content[item_id] for item_id in ids if item_id in content]
        if not parts:
            raise ValueError("no clips found")
        modes = {
            "plain": "\n\n".join(parts),
            "bullets": "\n".join(f"- {part}" for part in parts),
            "quote": "\n\n".join("\n".join(f"> {line}" for line in part.splitlines()) for part in parts),
            "json": json.dumps(parts, indent=2),
        }
        if mode not in modes:
            raise ValueError("mode must be plain, bullets, quote, or json")
        return modes[mode]

