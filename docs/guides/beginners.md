# Install Chilli without being technical

This guide is for people who have never rented a server. It takes about an hour, most of it waiting,
and costs about the price of a coffee a month. You type commands only by copying them from this page.

Prefer to be guided? Copy the prompt from [install-with-ai.md](install-with-ai.md) into Claude,
ChatGPT or another assistant, and it walks you through these same steps one at a time.

## What you will end up with

- A small rented computer on the internet (a **server**, often called a VPS) that runs Chilli all the time.
- Your own web address for it, for example `chilli.yourname.com`.
- A button on your iPhone that sends a screenshot there, and a "Chilli" entry in the share sheet for links.
- Claude (or another AI app) that can search everything you saved.

## What you need

| What | Typical cost | Notes |
| --- | --- | --- |
| A server (VPS) with 2 vCPU and 4 GB RAM, Ubuntu 24.04 | about 4-8 EUR / USD a month | Any provider works: Hetzner, DigitalOcean, OVH, Vultr, Linode... 2 GB RAM also works with swap (step 4). |
| A domain name | about 10-15 EUR / USD a year | Bought from any registrar (Cloudflare, Namecheap, OVH, IONOS, Porkbun...). A subdomain of a domain you already own is fine and free. |
| An API key for the AI model | pay per use | For Claude: an account at [console.anthropic.com](https://console.anthropic.com). Set a monthly spend limit there. |
| An iPhone with the Shortcuts app | | Android has no ready-made guide yet; the browser extension works on any computer. |
| A computer with a terminal | free | Mac: the **Terminal** app. Windows: **PowerShell** or **Windows Terminal**. |

Keep a password manager or a private note open. During the install you will get three secret values
(the model API key, the capture token and the MCP secret). Store them there and **never paste them
into a chat, a screenshot or a public place**: anyone with them can read or change your saves.

## Step 1. Rent the server

1. Create an account with a VPS provider and add a payment method.
2. Create a new server (it may be called "server", "droplet", "instance" or "VPS"):
   - Image / operating system: **Ubuntu 24.04**.
   - Size: 2 vCPU, 4 GB RAM (or 2 GB, then do step 4). 20 GB of disk is plenty.
   - Location: anywhere close to you.
   - Login: choose **SSH key** if you know how; otherwise a **root password** is fine for now.
     The provider shows or emails it to you.
3. When the server is running, copy its **public IPv4 address**, four numbers like `203.0.113.25`.
   It is shown on the server's page.

If the provider offers a firewall, allow incoming ports **22** (SSH), **80** and **443** (web).

## Step 2. Point your domain at the server

At the company where you bought the domain, open its **DNS settings** and add a record:

| Type | Name (host) | Value (points to) | TTL |
| --- | --- | --- | --- |
| `A` | `chilli` | your server's IPv4 address | default |

This makes `chilli.yourdomain.com` lead to your server. (Put `@` as the name instead to use the bare
domain itself.) If the provider has an orange cloud or "proxy" switch (Cloudflare), turn it **off** for
this record, so the server can get its HTTPS certificate.

It usually takes 5-30 minutes before the name works everywhere. You will check it in step 5.

## Step 3. Connect to the server

Open Terminal (Mac) or PowerShell (Windows) and type, with your server's address:

```bash
ssh root@203.0.113.25
```

- The first time it asks `Are you sure you want to continue connecting?`: type `yes` and press Enter.
- If you chose a password, paste it and press Enter. **Nothing appears while you type a password**;
  that is normal.
- You are in when the line ends with something like `root@your-server:~#`.

Everything from now on is typed **in this window**, on the server. To paste: Cmd+V on a Mac, right
click or Ctrl+Shift+V in Windows terminals. Paste one block at a time and wait until the prompt
(`#`) comes back before the next one.

## Step 4. Prepare the server

Update the system and install Docker (the tool that runs Chilli and its database). This takes a few
minutes:

```bash
apt update && apt -y upgrade
curl -fsSL https://get.docker.com | sh
docker compose version
```

The last line should print a version, such as `Docker Compose version v2...`.

**Only if your server has 2 GB of RAM or less**, add swap (extra memory on disk) so the first start
does not run out of memory:

```bash
fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
```

If your provider has no firewall of its own, turn on the one in Ubuntu (answer `y` when asked):

```bash
ufw allow OpenSSH && ufw allow 80 && ufw allow 443 && ufw enable
```

## Step 5. Check the domain

Replace the name with yours:

```bash
getent hosts chilli.yourdomain.com
```

It should print your server's IP address. If it prints nothing, wait 10 minutes and try again, and
check the DNS record from step 2. Do not continue until it shows the right address: the next step
needs it to get the HTTPS certificate.

## Step 6. Get a model API key

For Claude: sign in at [console.anthropic.com](https://console.anthropic.com), add credit under
**Billing** and set a monthly limit, then **API Keys** → **Create Key**. Copy the key (it starts with
`sk-ant-`) into your password manager. It is shown only once.

Other models (OpenAI, OpenRouter, Gemini, or a free local model in Ollama) work too, see
[configuration.md](configuration.md#model). If you are unsure, use Claude: it is the one tested live.

## Step 7. Install Chilli

```bash
cd /opt
git clone https://github.com/pawelmnowak1990-Now4czek/chilli.git
cd chilli
./setup.sh
```

The installer asks a few questions. Press Enter to accept the suggestion in brackets.

| Question | What to answer |
| --- | --- |
| Web server | Enter (`caddy`: it gets the HTTPS certificate for you) |
| Domain | `chilli.yourdomain.com`, without `https://` |
| Model provider | Enter (`anthropic`, for Claude) |
| Model | Enter |
| API key | paste the key from step 6 and press Enter (nothing is shown while you paste) |
| Language | the language you want summaries in: `en`, `pl`, `de`, `fr`, `es`... |
| Your name | your first name, or Enter to skip |

The first start downloads and builds everything and takes 3-10 minutes. At the end the installer
checks itself (lines with `OK`; a `WARN` is not fatal) and prints four values:

- **Capture URL** and **Capture token**: for the iPhone and the browser extension.
- **MCP URL** and **MCP header**: for Claude and other AI apps.

**Copy all four into your password manager now.** They are not shown again. (They are kept in the
file `/opt/chilli/.env` on the server; `grep TOKEN /opt/chilli/.env` shows the token later if you lose it.)

Check from your own computer's browser: open `https://chilli.yourdomain.com/health`. You should see a
short text with `"status":"ok"`. A padlock in the address bar means HTTPS works.

## Step 8. The iPhone button

Follow [ios-shortcuts.md](ios-shortcuts.md). In short, you build two Shortcuts in the Shortcuts app
(about five minutes), paste the capture URL and the token into them, and put the first one on the
Action Button (or on Back Tap: double-tap the back of the phone).

Test it: open any page, press the button, and wait for the "Saved to Chilli" notification.

## Step 9. Connect Claude

In claude.ai (web or the desktop app): **Settings** → **Connectors** → **Add custom connector**:

- Name: `Chilli`
- URL: the MCP URL from step 7, e.g. `https://chilli.yourdomain.com/mcp`
- Authentication: no sign-in, and add a header named `Authorization` with the value
  `Bearer ` followed by your MCP secret (the word Bearer, one space, the secret).

Custom connectors depend on your claude.ai plan; if you do not see the option, check Anthropic's help
pages. Other apps (Claude Code, Cursor, ChatGPT): [mcp-clients.md](mcp-clients.md).

Test it: in a new chat ask "What did I save to Chilli today?". The first time, Claude asks for
permission to use the connector.

Then tell Claude about your projects, so every save gets a usefulness score for each: "Add a Chilli
project 'Kitchen renovation' about planning a small kitchen on a budget."

## Step 10. Backups (recommended)

Your saves live only on this server. A nightly backup at 3:15 keeps 14 days of copies on the server:

```bash
(crontab -l 2>/dev/null; echo '15 3 * * * cd /opt/chilli && bash deploy/backup.sh >> /var/log/chilli-backup.log 2>&1') | crontab -
```

Many providers also sell automatic server snapshots for a small fee; turning them on protects you if
the whole server is lost. More: [install.md](install.md#back-up).

## Keeping it up to date

Every month or so, connect with `ssh` as in step 3 and run:

```bash
cd /opt/chilli && git pull && docker compose up -d --build
```

## When something goes wrong

| What you see | What to do |
| --- | --- |
| `ssh: connect ... timed out` | Wrong IP address, the server is off, or a firewall blocks port 22. Check the provider's page. |
| `Permission denied` on ssh | Wrong password. Many providers have a "reset root password" button. |
| `getent` prints nothing | The DNS record is missing, has a typo, or has not spread yet. Wait and check step 2. |
| `/health` does not open, or the browser warns about the certificate | The domain did not point at the server when Chilli started. Fix DNS, then run `cd /opt/chilli && docker compose restart caddy`. |
| The iPhone shows an alert instead of "Saved to Chilli" | Read the message: usually a mistyped token in the Shortcut. See the troubleshooting list in [ios-shortcuts.md](ios-shortcuts.md#troubleshooting). |
| A save never gets a title | The model key or its credit. Run `cd /opt/chilli && docker compose exec api python -m app.doctor` and read the `FAIL` lines. |
| A secret ended up in a chat or screenshot | Replace it: see the top of [configuration.md](configuration.md). |

Still stuck? Paste the **error message** (never your secrets) into the assistant you are using with
the prompt from [install-with-ai.md](install-with-ai.md), or open an
[issue](https://github.com/pawelmnowak1990-Now4czek/chilli/issues).
