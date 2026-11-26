"""Knowledge gaps: what an AI assistant looked for in Chilli and did not find (or found wrong).

The idea comes from Harrison Chase's "knowledge factory": agents that use the knowledge are the best
place to notice what is missing, but they should only report it, not fix it. Fixing is the owner's
job (one more save from the phone) and, later, a background curator's.

- report_gap: an assistant reports a gap. A question very close to an open one counts as a repeat
  (times_reported + 1) instead of a new row, so the list stays short. No model call, only a local
  embedding of the question.
- match_new_save: runs at the end of processing every save. When the new save is close in meaning
  to an open gap, the gap becomes a 'candidate' with that save in closed_by. It is not closed
  automatically: a wrong automatic close would hide the gap for good, so the owner confirms.
- list_gaps / resolve_gap: for the digests and for the owner ("yes, that answers it").
"""

from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from app.search import _jsonable

KINDS = ("missing", "wrong", "stale")
STATUSES = ("open", "candidate", "closed", "dismissed")

# Largest cosine distance between two questions that counts as the same question asked again.
# Both sides are "query:" embeddings, which sit closer to each other than a query and a passage,
# so this is stricter than GAP_MATCH_DISTANCE. A constant: a product decision, not configuration.
REPEAT_MAX_DISTANCE = 0.08

MAX_QUESTION_CHARS = 500
MAX_NOTE_CHARS = 2000

# Columns returned by list_gaps and report_gap. The candidate's title comes from saves (LEFT JOIN).
GAP_COLUMNS = """g.id, g.created_at, g.question, g.kind, g.context, g.suggestion, g.save_id,
    p.name AS project, g.times_reported, g.status, g.closed_by, c.title AS closed_by_title, g.closed_at"""
GAP_FROM = """knowledge_gaps g
    LEFT JOIN projects p ON p.id = g.project_id
    LEFT JOIN saves c ON c.id = g.closed_by"""


def _vector_text(vector: list[float]) -> str:
    """pgvector takes a vector as text '[0.1,0.2,...]', cast with ::vector in SQL."""
    return "[" + ",".join(str(x) for x in vector) + "]"


def _project_id(conn: psycopg.Connection, project: str | None) -> int | None:
    """Project name (any letter case) to its id. An unknown name is an error, like in top_saves."""
    if project is None or not project.strip():
        return None
    row = conn.execute("SELECT id FROM projects WHERE lower(name) = lower(%s)", (project.strip(),)).fetchone()
    if row is None:
        raise ValueError(f"no project {project!r} (see list_projects)")
    return row[0]


def _get_gap(conn: psycopg.Connection, gap_id: int) -> dict[str, Any] | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f"SELECT {GAP_COLUMNS} FROM {GAP_FROM} WHERE g.id = %s", (gap_id,))
        row = cur.fetchone()
    return _jsonable(row) if row is not None else None


def report_gap(
    conn: psycopg.Connection,
    question: str,
    question_vector: list[float],
    kind: str = "missing",
    context: str = "",
    suggestion: str = "",
    save_id: str | None = None,
    project: str | None = None,
) -> dict[str, Any]:
    """Stores a gap, or counts a repeat of an open one. Returns the gap with `repeated`
    (true = an existing gap was reported again)."""
    question = question.strip()
    if not question:
        raise ValueError("question is empty")
    if len(question) > MAX_QUESTION_CHARS:
        raise ValueError(f"question is longer than {MAX_QUESTION_CHARS} characters")
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}")
    context = context.strip()[:MAX_NOTE_CHARS]
    suggestion = suggestion.strip()[:MAX_NOTE_CHARS]
    save_uuid = UUID(save_id) if save_id else None  # a malformed id raises ValueError
    if save_uuid is not None and conn.execute("SELECT 1 FROM saves WHERE id = %s", (save_uuid,)).fetchone() is None:
        raise ValueError(f"no save {save_id}")
    project_id = _project_id(conn, project)
    vector = _vector_text(question_vector)

    # A repeat: the nearest gap that is still waiting (open or candidate) within REPEAT_MAX_DISTANCE.
    repeat = conn.execute(
        """SELECT id FROM knowledge_gaps
           WHERE status IN ('open', 'candidate') AND embedding IS NOT NULL
             AND embedding <=> %(vector)s::vector <= %(max_distance)s
           ORDER BY embedding <=> %(vector)s::vector
           LIMIT 1""",
        {"vector": vector, "max_distance": REPEAT_MAX_DISTANCE},
    ).fetchone()
    if repeat is not None:
        # Keep the first wording; fill in a suggestion or context only when the first report had none.
        conn.execute(
            """UPDATE knowledge_gaps
               SET times_reported = times_reported + 1,
                   suggestion = CASE WHEN suggestion = '' THEN %(suggestion)s ELSE suggestion END,
                   context = CASE WHEN context = '' THEN %(context)s ELSE context END
               WHERE id = %(id)s""",
            {"id": repeat[0], "suggestion": suggestion, "context": context},
        )
        gap_id, repeated = repeat[0], True
    else:
        row = conn.execute(
            """INSERT INTO knowledge_gaps (question, kind, context, suggestion, save_id, project_id, embedding)
               VALUES (%s, %s, %s, %s, %s, %s, %s::vector)
               RETURNING id""",
            (question, kind, context, suggestion, save_uuid, project_id, vector),
        ).fetchone()
        assert row is not None
        gap_id, repeated = row[0], False
    gap = _get_gap(conn, gap_id)
    assert gap is not None
    gap["repeated"] = repeated
    return gap


def list_gaps(
    conn: psycopg.Connection, status: str | None = "open", project: str | None = None, limit: int = 20
) -> list[dict[str, Any]]:
    """Gaps with the given status (None = every status), most often reported first, then newest."""
    if status is not None and status not in STATUSES:
        raise ValueError(f"status must be one of {', '.join(STATUSES)}")
    project_id = _project_id(conn, project)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"""SELECT {GAP_COLUMNS} FROM {GAP_FROM}
                WHERE (%(status)s::text IS NULL OR g.status = %(status)s)
                  AND (%(project_id)s::int IS NULL OR g.project_id = %(project_id)s)
                ORDER BY g.times_reported DESC, g.created_at DESC
                LIMIT %(limit)s""",
            {"status": status, "project_id": project_id, "limit": limit},
        )
        return [_jsonable(row) for row in cur.fetchall()]


def resolve_gap(conn: psycopg.Connection, gap_id: int, status: str, save_id: str | None = None) -> dict[str, Any]:
    """Changes a gap's status.

    closed: answered; by `save_id`, or by the candidate save already in closed_by.
    dismissed: not worth filling. open: back on the list (clears closed_by).
    """
    if status not in ("open", "closed", "dismissed"):
        raise ValueError("status must be open, closed or dismissed")
    save_uuid = UUID(save_id) if save_id else None
    if save_uuid is not None and conn.execute("SELECT 1 FROM saves WHERE id = %s", (save_uuid,)).fetchone() is None:
        raise ValueError(f"no save {save_id}")
    updated = conn.execute(
        """UPDATE knowledge_gaps
           SET status = %(status)s,
               closed_by = CASE WHEN %(status)s = 'open' THEN NULL
                                ELSE coalesce(%(save_id)s::uuid, closed_by) END,
               closed_at = CASE WHEN %(status)s = 'open' THEN NULL ELSE now() END
           WHERE id = %(id)s""",
        {"status": status, "save_id": save_uuid, "id": gap_id},
    ).rowcount
    if updated == 0:
        raise ValueError(f"no gap {gap_id}")
    gap = _get_gap(conn, gap_id)
    assert gap is not None
    return gap


def match_new_save(conn: psycopg.Connection, save_id: UUID, max_distance: float) -> list[int]:
    """Marks open gaps that the new save may answer as 'candidate'. Returns their ids.

    The save's embedding is a "passage:" vector and the gap's a "query:" vector, the same pairing as
    search and the browser extension's related saves, so the threshold is on the same scale as
    RELATED_MAX_DISTANCE. A hidden duplicate does not count (its link already did).
    """
    rows = conn.execute(
        """UPDATE knowledge_gaps g
           SET status = 'candidate', closed_by = s.id
           FROM saves s
           WHERE s.id = %(save_id)s AND s.embedding IS NOT NULL AND s.duplicate_of IS NULL
             AND g.status = 'open' AND g.embedding IS NOT NULL
             AND g.embedding <=> s.embedding <= %(max_distance)s
           RETURNING g.id""",
        {"save_id": save_id, "max_distance": max_distance},
    ).fetchall()
    return [row[0] for row in rows]
