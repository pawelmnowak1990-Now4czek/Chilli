"""Service configuration read from environment variables (the .env file).

Everything that differs between a laptop and the server, or is a secret, goes here rather
than into the code. That way changing the model or a key does not touch any logic.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Field names match the variable names in .env (case does not matter).
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "dev"

    # Public address of this server, e.g. https://chilli.example.com (no trailing slash).
    # The MCP server only accepts requests for this host (app/public_url.py), and the address is
    # included in the User-Agent when fetching pages. Empty = local use only.
    public_url: str = ""

    # Database connection; set automatically in docker compose.
    database_url: str = ""

    # Token the iOS Shortcut sends in a header with every capture.
    capture_token: str = ""

    # MCP server secret. The client sends it in the `Authorization: Bearer <secret>` header on /mcp.
    mcp_secret: str = ""
    # Whether the old /mcp/<secret> address still works. Once the connector uses the header: false.
    mcp_secret_in_url: bool = True

    # Language in which the model writes titles, summaries, tags and rating reasons, as an ISO 639-1
    # code (pl, en, de...). Transcribed text stays in its original language. See app/language.py.
    content_language: str = "en"
    # How prompts refer to the person who saves things; empty = "the owner".
    owner_name: str = ""

    # Model provider (app/llm/factory.py): "anthropic" (Claude) or "openai" (any server with an
    # OpenAI-compatible API: OpenAI, OpenRouter, Gemini, Ollama, LM Studio, vLLM).
    # A plain str rather than Literal, so an empty LLM_PROVIDER= line means the default instead
    # of a startup error; unknown values are rejected in the factory.
    llm_provider: str = "anthropic"
    # Model for text (links, rating) and, unless LLM_VISION_MODEL is set, for screenshots.
    llm_model: str = ""
    llm_vision_model: str = ""
    llm_api_key: str = ""
    # Server address for provider openai, e.g. http://ollama:11434/v1. Empty = OpenAI itself.
    llm_base_url: str = ""

    # Older names, still read for compatibility: with LLM_* empty, provider anthropic uses
    # ANTHROPIC_API_KEY and VISION_MODEL (empty = default model from app/llm/factory.py).
    anthropic_api_key: str = ""
    vision_model: str = ""
    # How hard Claude should "think": low is enough to transcribe and summarize a screenshot.
    # Anthropic only; ignored by provider openai.
    vision_effort: str = "low"

    # Local embedding model; switching to a model with a different dimension requires changing
    # the database column.
    embedding_model: str = "intfloat/multilingual-e5-small"
    # Where the embedding model files live. In Docker the model is downloaded when the image is built.
    embedding_cache_dir: str = "/srv/models"

    # Directory for downscaled copies of screenshots.
    images_dir: str = "/data/images"

    # Longer side of the stored screenshot copy (and of the image sent to Claude). 1568 px is the
    # value older Claude model docs gave as a sensible maximum; not verified for the current model.
    # If small text is misread, raise IMAGE_MAX_SIDE in .env.
    image_max_side: int = 1568

    # Largest accepted image in MB. An iPhone screenshot is usually 2-6 MB.
    # nginx lets through up to 25 MB (deploy/nginx/chilli.conf.template), so this is lower.
    max_upload_mb: int = 15

    # Largest cosine distance (0 = identical) at which a save counts as related to the page
    # open in the browser extension (app/related.py). Lower = fewer, but more accurate.
    related_max_distance: float = 0.15

    # Largest cosine distance between a new save and an open knowledge gap (app/gaps.py) at which
    # the save is offered as a possible answer. Same scale as related_max_distance (a question
    # against a save), so the same tested value; lower = fewer, more accurate candidates.
    gap_match_distance: float = 0.15

    # How often, in hours, the service fetches subscribed RSS feeds (app/feeds.py). 0 disables it.
    feed_poll_hours: float = 6

    # X (Twitter) bookmarks import (app/x_bookmarks.py, docs/guides/x-bookmarks.md). Both empty =
    # the feature is off: /x/connect and /x/callback answer 404 and no poller thread starts.
    x_client_id: str = ""
    x_client_secret: str = ""
    # How often, in minutes, new bookmarks are fetched. 0 disables polling.
    x_bookmarks_poll_minutes: float = 30
    # First sync: true = import every bookmark X still returns (up to about 800);
    # false = only mark the current ones as seen, so only bookmarks added later come in.
    x_bookmarks_backfill: bool = False


# One shared instance imported by the rest of the code.
settings = Settings()
