"""Export of all saves into one ZIP file: data to take with you.

Inside:
- saves.json: the list of saves, all columns except the `embedding` vector (it can be recomputed
  from the text, and in JSON it would take the most space) plus project ratings (`projects`),
- markdown/<date>-<title>-<id>.md: every save as a note to read or to drop into another
  tool (Obsidian, Notion); the image is linked with a relative path,
- images/<id>.webp: the stored copies of screenshots.

Running on the server (the file lands in the host's current directory):
    docker compose exec -T api python -m app.export > chilli-export.zip

-T turns off the terminal in `docker compose exec`, otherwise the ZIP bytes would get corrupted.
"""

import json
import re
import sys
import unicodedata
import zipfile
from pathlib import Path
from typing import IO, Any

import psycopg
from psycopg.rows import dict_row

# All columns except the vector. An explicit list, so that a new column does not slip into the export by accident.
EXPORT_COLUMNS = """id, created_at, source_type, image_path, url, source_app, title, summary,
    content_text, kind, tags, status, note, processed_at, error, duplicate_of,
    page_text, remind_at, rated_at"""

# Letters that unicodedata does not decompose into a plain letter (ł is a separate letter, not l with a stroke).
SLUG_LETTERS = str.maketrans({"ł": "l", "Ł": "l", "ø": "o", "ß": "ss"})


def _jsonable(value: Any) -> Any:
    """UUIDs and dates as text; the rest (text, numbers, tag lists) passes through unchanged."""
    if value is None or isinstance(value, (str, int, float, bool, list)):
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def slugify(text: str, max_length: int = 50) -> str:
    """Title as a part of a file name: lowercase letters without diacritics, digits and hyphens."""
    ascii_text = unicodedata.normalize("NFKD", text.translate(SLUG_LETTERS)).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    return slug[:max_length].rstrip("-") or "save"


def to_markdown(record: dict[str, Any]) -> str:
    """One save as a Markdown note: title, metadata as a list, summary, content, page copy."""
    lines = [f"# {record['title'] or '(untitled)'}", ""]
    meta = [
        ("date", record["created_at"]),
        ("type", f"{record['source_type']}, {record['kind']}" if record["kind"] else record["source_type"]),
        ("url", record["url"]),
        ("source", record["source_app"]),
        ("tags", ", ".join(record["tags"] or [])),
        ("status", record["status"]),
        ("reminder", record["remind_at"]),
        ("id", record["id"]),
    ]
    lines += [f"- {label}: {value}" for label, value in meta if value]
    if record["projects"]:
        lines += ["", "## Projects", ""]
        lines += [f"- {p['project']}: {p['score']}/10, {p['reason']}" for p in record["projects"]]
    if record["image_file"]:
        # Notes live in markdown/, images in images/: hence "../".
        lines += ["", f"![screenshot](../{record['image_file']})"]
    for heading, key in (("Summary", "summary"), ("Note", "note"), ("Content", "content_text")):
        if record[key]:
            lines += ["", f"## {heading}", "", record[key]]
    if record["page_text"] and record["page_text"] != record["content_text"]:
        lines += ["", "## Page copy", "", record["page_text"]]
    return "\n".join(lines) + "\n"


def _ratings(conn: psycopg.Connection) -> dict[str, list[dict[str, Any]]]:
    """Ratings of all saves at once, grouped by save id (one query instead of a thousand)."""
    rows = conn.execute(
        """SELECT sp.save_id::text, p.name, sp.score, sp.reason
           FROM save_projects sp JOIN projects p ON p.id = sp.project_id
           ORDER BY sp.score DESC, p.name"""
    ).fetchall()
    grouped: dict[str, list[dict[str, Any]]] = {}
    for save_id, name, score, reason in rows:
        grouped.setdefault(save_id, []).append({"project": name, "score": score, "reason": reason})
    return grouped


def write_export(conn: psycopg.Connection, out: IO[bytes]) -> int:
    """Writes the ZIP to `out` (a file or a stream). Returns the number of exported saves."""
    with conn.cursor(row_factory=dict_row) as cur:
        # local_date: the day of the save in Warsaw, for the Markdown file name (it is not in the JSON).
        cur.execute(
            f"""SELECT {EXPORT_COLUMNS}, (created_at AT TIME ZONE 'Europe/Warsaw')::date AS local_date
                FROM saves ORDER BY created_at"""
        )
        rows = cur.fetchall()
    ratings = _ratings(conn)

    records = []
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for row in rows:
            local_date = row.pop("local_date")
            record = {key: _jsonable(value) for key, value in row.items()}
            record["projects"] = ratings.get(record["id"], [])
            image = Path(row["image_path"]) if row["image_path"] else None
            if image is not None and image.is_file():
                # In the archive the image is named after the save id; the server path would mean nothing.
                name = f"images/{row['id']}{image.suffix}"
                archive.write(image, name)
                record["image_file"] = name
            else:
                record["image_file"] = None
            records.append(record)
            name = f"markdown/{local_date}-{slugify(record['title'] or '')}-{record['id'][:8]}.md"
            archive.writestr(name, to_markdown(record))
        archive.writestr("saves.json", json.dumps(records, ensure_ascii=False, indent=2))
    return len(records)


def main() -> None:
    from app import db

    with db.connect() as conn:
        count = write_export(conn, sys.stdout.buffer)
    # Message on stderr, so it does not end up in the ZIP file redirected from stdout.
    print(f"saves exported: {count}", file=sys.stderr)


if __name__ == "__main__":
    main()
