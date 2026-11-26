# 28. Install guides for non-technical people

Two user guides for people who have never rented a server, written before the repository went public.

## What was built

- `docs/guides/beginners.md`: ten steps from renting a VPS to a working Action Button and a claude.ai
  connector: choosing a server, a DNS A record, `ssh`, Docker through `get.docker.com`, swap and
  `ufw`, checking DNS with `getent hosts` before Caddy asks for a certificate, a Claude API key,
  `./setup.sh` with an answer for each question, the Shortcuts, the connector, a nightly backup, updates
  and a table of common failures. Commands are copied from `install.md` and `setup.sh`, so there is
  one source of truth for anything technical.
- `docs/guides/install-with-ai.md`: a prompt to paste into any assistant (Claude, ChatGPT, Gemini...).
  It tells the assistant to guide one step at a time and wait for the output, to never ask for
  secrets (API key, `CAPTURE_TOKEN`, `MCP_SECRET`), to treat README and docs/guides/ as the source of
  truth when it can browse, and it carries the steps and troubleshooting inline for assistants that
  cannot. For agents that run commands themselves, the owner still runs `./setup.sh`, because its
  output contains the tokens.
- Links from the README (Quick start and Guides) and from the top of `install.md`.

## How to check

Read both guides against `setup.sh` (question order, printed values) and `install.md`. Nothing to run;
no code changed. Worth a live pass on a clean VPS by someone new to servers before announcing.
