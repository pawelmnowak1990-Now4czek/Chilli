# Krok 6: serwer MCP

Co powstało:

- `app/mcp_server.py`: serwer MCP (SDK `mcp` 2.x, transport Streamable HTTP, bez sesji) pod adresem
  `https://chilli.example.com/mcp/<MCP_SECRET>`. Bez `MCP_SECRET` w `.env` serwer MCP nie jest wystawiany wcale.
- Narzędzia:
  - `search_saves(query, limit, status)`: wyszukiwanie hybrydowe (pełnotekstowe + po znaczeniu, Reciprocal Rank Fusion),
  - `get_save(save_id)`: pełny zapis z całym tekstem,
  - `list_recent(days, status, limit)`: ostatnie zapisy (do podsumowania tygodnia),
  - `set_status(save_id, status, note)`: `nowy` / `przejrzany` / `wykorzystany` / `archiwum` + notatka.
- `app/search.py`: jawny SQL tych zapytań.
- Sekret poza logami: nginx ma `access_log off` dla `/mcp`, a uvicorn loguje `/mcp/***` (filtr w `app/main.py`).
- Ochrona przed DNS rebinding: serwer MCP odpowiada tylko na nagłówek Host `chilli.example.com` (i localhost).

Sprawdzone lokalnie 20.11.2026: initialize, `list_recent`, `search_saves` z prawdziwym modelem embeddingów, 404 dla złego sekretu, brak sekretu w logu.

## Na serwerze

```bash
cd /opt/chilli && git pull && docker compose up -d --build
SECRET=$(grep '^MCP_SECRET=' .env | cut -d= -f2)
curl -s -H "Accept: application/json, text/event-stream" -H "Content-Type: application/json" \
  "https://chilli.example.com/mcp/$SECRET" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"list_recent","arguments":{"days":3}}}' | head -c 300; echo
docker compose logs --tail 5 api     # w logu ma być /mcp/***, nie sekret
```

## Podpięcie w Claude

claude.ai → Ustawienia → Konektory → Dodaj własny konektor:
- nazwa: `Chilli`
- adres: `https://chilli.example.com/mcp/<MCP_SECRET>` (sekret z `grep '^MCP_SECRET=' /opt/chilli/.env`)
- bez OAuth (sekretny adres to cały dostęp; nie udostępniaj go nikomu).

Test w rozmowie: „Poszukaj w Chilli, co zapisałem o Anthropic".

## Czego testy nie sprawdziły

- Połączenia samego Claude (konektor) z serwerem przez nginx i HTTPS.
- Jakości wyszukiwania na większej liczbie zapisów (na razie kilka).

Wdrożone 20.11.2026: test przez HTTPS z serwera OK, konektor „Chilli" (No sign-in) dodany w claude.ai i działa w rozmowie.
