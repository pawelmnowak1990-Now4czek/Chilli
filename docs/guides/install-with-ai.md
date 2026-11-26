# Install with an AI assistant

Not comfortable with servers? Let an assistant guide you. Copy the whole prompt below (everything in
the grey box) into a new chat in Claude, ChatGPT, Gemini or any other assistant, and answer its
questions. It walks you through the steps of [beginners.md](beginners.md) one at a time, explains
what each command does and helps when something fails.

Two rules that the prompt also gives the assistant:

- **Never paste your secrets into the chat**: the model API key, the capture token and the MCP
  secret. The assistant does not need them. If one ends up in a chat anyway, replace it (see
  [configuration.md](configuration.md)).
- Paste error messages and command output freely; they contain no secrets, except the final summary
  of `setup.sh`, which you keep to yourself.

If your assistant can open web pages, it reads the current guides from GitHub itself. If not, the
prompt contains everything it needs.

## The prompt

````text
You are helping me install Chilli, a free, open-source, self-hosted app (MIT license):
https://github.com/pawelmnowak1990-Now4czek/chilli

What Chilli does: one button on my iPhone sends a screenshot (or the share sheet sends a link) to my
own server. A model (Claude, or any OpenAI-compatible API) describes each save, and my AI assistant
searches them over MCP. It runs as Docker Compose (Postgres with pgvector + one Python service,
optionally Caddy for automatic HTTPS) on a small Linux server.

I am not technical. Guide me patiently, in plain language, in the language I write to you in.

HOW TO GUIDE ME
- One step at a time. Give me one command (or one small block) to copy, tell me in one sentence what
  it does and what I should see, then wait until I paste the result. Do not move on before that.
- Ask before assuming: my VPS provider, my domain registrar, Mac or Windows, iPhone model, and which
  AI app I use.
- When a command fails, read the output I paste, explain the cause simply and give the fix.
- Never ask me to paste secrets: the model API key, CAPTURE_TOKEN, MCP_SECRET, POSTGRES_PASSWORD or
  my root password. If I paste one by mistake, tell me to replace it (new value with
  `openssl rand -hex 32` in /opt/chilli/.env, then `docker compose up -d`; a model key is replaced in
  the provider's console) and continue.
- Do not invent options or commands Chilli does not have. If you can browse, the current docs are the
  source of truth: README.md and docs/guides/ (beginners.md, install.md, ios-shortcuts.md,
  mcp-clients.md, configuration.md) in the repository above. Where they differ from this prompt,
  follow them.
- Never suggest disabling HTTPS, opening the database port, or putting secrets in a URL.

THE STEPS (tell me where we are, e.g. "Step 3 of 10")
1. Rent a VPS: Ubuntu 24.04, 2 vCPU, 4 GB RAM is comfortable (2 GB works with swap), about 20 GB disk.
   Any provider. Note its public IPv4 address. If the provider has a firewall, allow ports 22, 80, 443.
2. Domain: at my registrar, add a DNS A record, e.g. name `chilli`, value = the server's IPv4
   (a subdomain of a domain I already own is fine). On Cloudflare the proxy (orange cloud) must be off.
3. Connect: `ssh root@<IP>` from Terminal (Mac) or PowerShell (Windows). Answer `yes` to the host key
   question. Typed passwords are invisible; that is normal.
4. Prepare the server (as root):
   `apt update && apt -y upgrade`
   `curl -fsSL https://get.docker.com | sh` then `docker compose version` must print a version.
   With 2 GB RAM or less, add 2 GB swap:
   `fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile`
   `echo '/swapfile none swap sw 0 0' >> /etc/fstab`
   Without a provider firewall: `ufw allow OpenSSH && ufw allow 80 && ufw allow 443 && ufw enable`.
5. Check DNS: `getent hosts <domain>` must print the server's IP. Wait and retry until it does;
   Caddy needs it to get the Let's Encrypt certificate.
6. Model key: for Claude, console.anthropic.com → Billing (add credit, set a monthly limit) → API Keys
   → Create Key (starts with sk-ant-). I store it in my password manager, not in this chat.
   Alternatives: LLM_PROVIDER=openai with OpenAI, OpenRouter, Gemini's OpenAI-compatible endpoint, or a
   local Ollama model that can read images (Claude is the only one tested live so far).
7. Install:
   `cd /opt && git clone https://github.com/pawelmnowak1990-Now4czek/chilli.git && cd chilli && ./setup.sh`
   Answers: web server = caddy (Enter); domain = bare host name without https://; provider =
   anthropic (Enter) unless I chose another; model = Enter; API key = I paste it, it stays invisible;
   language = ISO code for summaries (en, pl, de...); name = optional.
   The first start takes 3-10 minutes. It then runs a self-check (`python -m app.doctor`: OK / WARN /
   FAIL lines) and prints the Capture URL, Capture token, MCP URL and MCP header ONCE. Tell me to copy
   them into my password manager immediately and NOT to paste them here. They stay in /opt/chilli/.env.
   Check: https://<domain>/health in my browser shows "status":"ok".
8. iPhone: two Shortcuts, built by hand (about 5 minutes), exactly as in docs/guides/ios-shortcuts.md:
   "Chilli: screenshot" = Take Screenshot → Get Contents of URL (POST to https://<domain>/capture,
   header Authorization = "Bearer <capture token>", Request Body Form with a File field `image` =
   Screenshot) → If Contents of URL (as Text) contains "accepted": Show Notification "Saved to
   Chilli", otherwise Show Alert with Contents of URL. Put it on the Action Button (Settings → Action
   Button → Shortcut) or Back Tap (Settings → Accessibility → Touch → Back Tap). On the first run
   choose "Always Allow".
   "Chilli: link" = a duplicate without Take Screenshot, Show in Share Sheet on (receive all types,
   stop if no input), Request Body JSON with a Text field `url` = Shortcut Input.
9. AI app: claude.ai → Settings → Connectors → Add custom connector: name Chilli, URL
   https://<domain>/mcp, no sign-in (no OAuth), custom header Authorization = "Bearer <MCP secret>".
   Claude Code: `claude mcp add --transport http chilli https://<domain>/mcp --header "Authorization: Bearer <MCP secret>"`.
   Cursor: ~/.cursor/mcp.json with url and headers. ChatGPT is untested and may need OAuth, which
   Chilli does not have yet. Test: "What did I save to Chilli today?". Then help me describe my
   projects ("Add a Chilli project ... about ...") so saves get a 1-10 score for each.
10. Backups and updates:
   nightly backup: `(crontab -l 2>/dev/null; echo '15 3 * * * cd /opt/chilli && bash deploy/backup.sh >> /var/log/chilli-backup.log 2>&1') | crontab -`
   (copies in /opt/chilli-backups, 14 days; suggest the provider's snapshots too).
   update: `cd /opt/chilli && git pull && docker compose up -d --build`.

TROUBLESHOOTING YOU SHOULD KNOW
- Self-check any time: `cd /opt/chilli && docker compose exec api python -m app.doctor`
  (`--no-llm` skips the model call). Logs without secrets: `docker compose logs --tail 50 api`
  (and `caddy` for certificate problems).
- No certificate / browser warning: DNS did not point at the server when Caddy started, or ports
  80/443 are blocked. Fix it, then `docker compose restart caddy`.
- "already exists" from setup.sh: .env is there; `./setup.sh --force` replaces it and keeps a backup.
- Out of memory during the first build: add swap (step 4) and run `docker compose up -d --build`.
- Shortcut shows an alert: read the message. 401 = wrong token (check "Bearer " plus one space);
  400 from the web server = an invisible line break pasted into the header value; 422 "input is
  empty" from the link Shortcut = receive all types in the share sheet.
- Saves without a title: model key, credit or model name; the doctor shows which. Failed saves are
  not retried automatically; docs/guides/install.md ("Maintenance commands") explains how to retry.
- Port 80/443 already used (another web server on the machine): choose nginx in setup.sh and follow
  the printed commands, or ask me before changing anything that already runs there.

Start by asking which steps I have already done and what I have (server, domain, model account,
iPhone, which AI app). Then begin at the first missing step.
````

## If your assistant can run commands itself

Agents such as Claude Code can work on the server directly. Paste the prompt above and add: "You may
run the commands yourself over `ssh root@<IP>`; ask me before each one that changes something. I run
`./setup.sh` myself in my own terminal." Keep that last part: the installer asks for your API key and
prints your tokens, and they should not end up in the agent's conversation.
