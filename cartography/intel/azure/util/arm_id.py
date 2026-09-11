"""Resolve ARM resource id references against the ids already stored in the graph.

ARM resource ids are case-insensitive and Azure is not consistent about the casing it
returns: the same resource can come back spelled differently from two API calls. The
matchers `load_matchlinks()` generates compare with exact property equality, so a
reference whose casing differs from its target node silently produces no edge, on every
sync, with no error.
"""

import neo4j


def stored_ids(neo4j_session: neo4j.Session, node_label: str) -> dict[str, str]:
    """Every id stored under ``node_label``, keyed by its lowercased form."""
    rows = neo4j_session.run(f"MATCH (n:{node_label}) RETURN n.id AS id")
    return {row["id"].lower(): row["id"] for row in rows if row.get("id")}


def resolve(rows: list[dict], keys: tuple[str, ...], ids: dict[str, str]) -> list[dict]:
    """Rewrite ``keys`` in each row to the spelling the graph stores.

    A reference with no match is left alone: it names a resource outside this ingestion,
    and recasing it would not make it resolve.
    """
    for row in rows:
        for key in keys:
            stored = ids.get(str(row.get(key, "")).lower())
            if stored:
                row[key] = stored
    return rows
