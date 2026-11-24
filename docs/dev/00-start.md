# Krok 0: szkielet

Co jest: struktura repo, schemat bazy, docker compose z Postgres + pgvector, serwis FastAPI z `/health`.

## Stan serwera (sprawdzone 19.11.2026)

- 3,7 GB RAM (2,5 GB dostępne), 2 vCPU, 23 GB wolnego dysku, brak swapu.
- nginx 1.24 na hoście zajmuje porty 80 i 443; strony w `/etc/nginx/sites-enabled`: `default` i jedna inna strona.
- certbot jest zainstalowany i obsługuje certyfikat innej strony na tym serwerze.
- System zgłasza „System restart required".

## Do zrobienia na serwerze przed krokiem 1

- [ ] Restart VPS w chwili, gdy drugi pipeline nie pracuje.
- [ ] Dodać 2 GB swapu.
- [ ] Rekord DNS typu A: `chilli` → adres VPS.
- [ ] Plik nginx dla `chilli.example.com` (proxy na `127.0.0.1:8000`, większy `client_max_body_size`, bez logowania `/mcp`) i certyfikat z certbota.
- [ ] Klucz API Claude do `.env` na serwerze.

Sprawdzone i zamknięte: porty 80 i 443 (nginx na hoście, Chilli dopina się jako kolejna strona).
