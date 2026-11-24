"""Rating how useful a save is for the owner's projects: the save's text and the project list go in,
matching projects with a 1-10 score and a short reason come out.

A separate, cheap call after a save is processed (text only, no image and no page fetch).
That way the rating can be repeated for old saves when the project list changes (app/rerate.py).
RSS entries are rated with the same call (app/feeds.py).
The reasons are written in CONTENT_LANGUAGE, the owner is named by OWNER_NAME (app/language.py).
"""

from dataclasses import dataclass

from pydantic import BaseModel, Field

from app import language
from app.config import settings
from app.llm import LLMProvider, LLMRefusal, TextPart
from app.llm import factory

# The beginning of the content is enough for rating; title, summary and tags carry the most.
MAX_CHARS_FOR_MODEL = 6_000


@dataclass
class Project:
    """A project as the model sees it: name and description (the id stays on the database side)."""

    id: int
    name: str
    description: str


class ProjectMatch(BaseModel):
    # The 1-10 range is not enforced in the schema (structured outputs do not guarantee min/max);
    # it is clamped in Python in clean_matches.
    project: str = Field(description="Project name exactly as on the list.")
    score: int = Field(description="Usefulness for this project, from 1 (barely) to 10 (very).")
    reason: str = Field(description="One short sentence: what it will be useful for in this project.")


class RelevanceRating(BaseModel):
    matches: list[ProjectMatch] = Field(description="Only projects the save can really help; may be empty.")


SYSTEM_PROMPT_TEMPLATE = """{owner_capitalized} saves screenshots and links to a personal knowledge base. You rate \
which of {owner}'s projects a given save may be useful for, and how much.

Scale: 1-3 loose connection, 4-6 may be useful, 7-8 will clearly help, 9-10 must be used.
List only projects the save is really connected to; when it fits none, return an empty list.
Copy project names exactly from the list.
Write each reason in {language}."""


def system_prompt(language_name: str, owner: str) -> str:
    """The system prompt for a given output language ("Polish") and owner label ("the owner")."""
    return SYSTEM_PROMPT_TEMPLATE.format(language=language_name, owner=owner, owner_capitalized=owner[:1].upper() + owner[1:])


@dataclass
class Rating:
    """A checked rating, ready to be stored in the save_projects table."""

    project_id: int
    score: int
    reason: str


class RelevanceRefusal(LLMRefusal):
    """The model (including the fallback model) refused to rate."""


def build_prompt(title: str, summary: str, tags: list[str], content: str, projects: list[Project]) -> str:
    project_lines = "\n".join(f"- {p.name}: {p.description}" for p in projects)
    return (
        f"Projects:\n{project_lines}\n\n"
        f"Save:\nTitle: {title}\nSummary: {summary}\nTags: {', '.join(tags)}\n\n"
        f"Content (beginning):\n{content[:MAX_CHARS_FOR_MODEL]}"
    )


def rate_save(
    title: str,
    summary: str,
    tags: list[str],
    content: str,
    projects: list[Project],
    provider: LLMProvider | None = None,
) -> list[Rating]:
    """Asks the model for a rating and returns only valid entries: a known project, the score clamped
    to 1-10, each project once. Without active projects there is nothing to rate, so no call is made."""
    if not projects:
        return []
    if provider is None:
        provider = factory.get_provider()
    system = system_prompt(language.language_name(settings.content_language), language.owner_label(settings.owner_name))
    try:
        output = provider.parse(
            system=system,
            content=[TextPart(build_prompt(title, summary, tags, content, projects))],
            schema=RelevanceRating,
            max_tokens=4000,
            model=factory.text_model(),
        )
    except LLMRefusal as error:
        raise RelevanceRefusal("the model refused to rate") from error
    return clean_matches(output.matches, projects)


def clean_matches(matches: list[ProjectMatch], projects: list[Project]) -> list[Rating]:
    """The model may get the letter case wrong, invent a project or give an 11. This is cleaned up here."""
    by_name = {p.name.strip().lower(): p for p in projects}
    ratings: dict[int, Rating] = {}
    for match in matches:
        project = by_name.get(match.project.strip().lower())
        if project is None:
            continue  # the project is not on the list: skipped
        score = max(1, min(10, match.score))
        # The same project twice: the higher score stays.
        if project.id not in ratings or ratings[project.id].score < score:
            ratings[project.id] = Rating(project_id=project.id, score=score, reason=match.reason.strip())
    return list(ratings.values())
