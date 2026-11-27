"""Own sites: pages the owner publishes themselves, so their content is not treated as a find.

A project can list its own sites (a product's website, its changelog, the owner's repository).
A save or an RSS entry from one of them stays searchable, but it is marked with `own_project` and
left out of the "best" lists: top_saves, from_archive and feed_highlights. Without this, the owner's
own changelog comes back in the morning summary as a 9/10 idea for the very project that wrote it.

The matching itself happens in SQL (functions url_site and own_project in db/schema.sql), so every
query can use it. This file only cleans up what the owner types before it is stored.
"""

import re

# What one entry may look like after cleaning: a domain with at least one dot, optionally followed
# by a path. Letters, digits and the few characters URLs use; no spaces, no query string.
_ENTRY = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+)+(/[a-z0-9._~%@+-]+)*$")

# A project with hundreds of own sites is more likely a mistake than a plan.
MAX_SITES = 50


def normalize_site(raw: str) -> str:
    """'https://www.Example.com/Blog/' -> 'example.com/blog'. Raises ValueError when it is not a site.

    Mirrors the SQL function url_site: lowercase, no scheme, no 'www.', no port, no query string,
    no trailing slash. Paths are compared without case, as url_site lowercases them too.
    """
    site = raw.strip().lower()
    site = re.sub(r"^[a-z][a-z0-9+.-]*://", "", site)  # scheme: https://, http://
    site = re.split(r"[?#]", site, maxsplit=1)[0]  # query string and fragment
    site = re.sub(r"^[^/@]*@", "", site)  # user:password@ in front of the host
    host, slash, path = site.partition("/")
    host = host.split(":", 1)[0]  # port
    host = host.removeprefix("www.")
    site = host + slash + path
    site = site.rstrip("/")
    if not _ENTRY.match(site):
        raise ValueError(f"{raw!r} is not a domain like example.com or a domain with a path like github.com/owner")
    return site


def normalize_sites(raw_sites: list[str]) -> list[str]:
    """Cleans every entry, drops repeats and keeps the owner's order."""
    cleaned: list[str] = []
    for raw in raw_sites:
        if not raw.strip():
            continue
        site = normalize_site(raw)
        if site not in cleaned:
            cleaned.append(site)
    if len(cleaned) > MAX_SITES:
        raise ValueError(f"at most {MAX_SITES} own sites per project")
    return cleaned
