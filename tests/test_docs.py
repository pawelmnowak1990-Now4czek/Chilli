"""Documentation: relative links point at files that exist, and every guide is linked from the README."""

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
DOCS = [REPO / "README.md", REPO / "shortcuts" / "README.md", *sorted((REPO / "docs" / "guides").glob("*.md")), *sorted((REPO / "docs" / "dev").glob("*.md"))]

PENDING_ASSET = (REPO / "docs" / "assets" / "demo.gif").resolve()

# [text](target) in Markdown, without images' alt text handling (same syntax).
LINK = re.compile(r"\]\(([^)\s]+)\)")


def relative_links(path: Path) -> list[str]:
    text = re.sub(r"```.*?```", "", path.read_text(encoding="utf-8"), flags=re.S)  # code blocks are not links
    return [t for t in LINK.findall(text) if not re.match(r"^[a-z]+:", t) and not t.startswith("#")]


@pytest.mark.parametrize("path", DOCS, ids=lambda p: str(p.relative_to(REPO)))
def test_relative_links_resolve(path: Path) -> None:
    missing = []
    for target in relative_links(path):
        file_part = target.split("#", 1)[0]
        # The demo GIF is recorded separately (docs/assets/README.md); only this one asset may be missing.
        if (path.parent / file_part).resolve() == PENDING_ASSET:
            continue
        if not (path.parent / file_part).exists():
            missing.append(target)
    assert not missing, f"{path.relative_to(REPO)}: {missing}"


def test_all_guides_are_linked_from_the_readme() -> None:
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    for guide in (REPO / "docs" / "guides").glob("*.md"):
        assert f"docs/guides/{guide.name}" in readme, guide.name
