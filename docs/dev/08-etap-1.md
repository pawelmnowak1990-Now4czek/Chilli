# Etap 1 roadmapy: porządki po MVP

Zakres z roadmapy (https://claude.ai/artifact/JuPizpTytFzMQtoE9YYPki, „Etap 1"). Roadmapa stawia ten etap
po bramie z 11.12.2026; właściciel zdecydował 20.11.2026, żeby zrobić go od razu.

Co powstało:

1. **Sekret MCP w nagłówku** (`app/mcp_auth.py`). Serwer MCP słucha pod `/mcp` i wpuszcza żądania
   z nagłówkiem `Authorization: Bearer <MCP_SECRET>`. Stary adres `/mcp/<MCP_SECRET>` działa dalej,
   dopóki w `.env` nie ustawisz `MCP_SECRET_IN_URL=false`.
2. **Łączenie duplikatów** (`app/dedupe.py`). Zrzut i link tego samego wpisu: zrzut dostaje
   `duplicate_of = <id linku>` i znika z `search_saves` i `list_recent`. `get_save` linku pokazuje
   schowane zrzuty (`duplicates`), a `get_save` zrzutu jego link (`duplicate_of`). Nic nie jest kasowane.
   Reguła: ten sam pełny adres (nie sama domena) albo oba zapisy z tej samej godziny i podobieństwo
   tytułu ze streszczeniem co najmniej 0,90. Progi dobrane na 14 zapisach z 19-20.11.2026: pary
   zrzut+link tego samego posta 0,91-0,97, wyraźnie różne tematy najwyżej 0,865. Jedna para tego
   samego długiego posta (dalszy fragment na zrzucie, 0,876) się nie połączy; to świadomy wybór.
   Adresy porównujemy bez parametrów śledzących (`?s=12`, `utm_*`), ale z resztą (`?v=` w YouTube).
   Schowany zrzut dalej bierze udział w wyszukiwaniu: trafienie w jego tekst zwraca link.
3. **Nowa kolumna bez ręcznego SQL.** Serwis przy starcie wykonuje `db/schema.sql` (wszystko
   z `IF NOT EXISTS`), więc kolumna `duplicate_of` sama dojdzie do bazy na serwerze.
   Test `tests/test_schema_upgrade.py` sprawdza to na schemacie z MVP.
4. **Eksport** (`app/export.py`): ZIP z `saves.json` (wszystko oprócz wektora) i obrazami.
   Od 24.11.2026 także `markdown/`: każdy zapis jako notatka Markdown (metadane, oceny dla projektów,
   streszczenie, treść, kopia strony, link do obrazu), a w JSON dodatkowo `projects`, `page_text`,
   `remind_at` i `rated_at`.
5. **Kopia zapasowa** (`deploy/backup.sh`): `pg_dump` bazy i archiwum obrazów do `/opt/chilli-backups`,
   kopie starsze niż 14 dni usuwane, opcjonalna wysyłka rsync na zewnętrzny serwer (`BACKUP_REMOTE` w `.env`).

Testy: `.venv/bin/pytest -q` → 79 passed (z etapem 2: 89).

## Na serwerze (po merge'u PR do main)

Uwaga przy kopiowaniu wyników do wątku: przed kopiowaniem zrób `clear` i nie wklejaj linii z sekretem.

```bash
cd /opt/chilli && git pull && docker compose up -d --build
docker compose exec db psql -U chilli -d chilli -c "\d saves" | grep duplicate_of
curl -s https://chilli.example.com/health; echo
```

Ma się pojawić linia z `duplicate_of | uuid` i `"db":"ok"`.

### Duplikaty w zapisach sprzed zmiany (jednorazowo)

Najpierw podgląd, nic nie zapisuje:

```bash
docker compose exec api python -m app.dedupe
```

Jeśli pary się zgadzają, połącz naprawdę:

```bash
docker compose exec api python -m app.dedupe --apply
```

Cofnięcie jednego połączenia: `UPDATE saves SET duplicate_of = NULL WHERE id = '<id zrzutu>';`.

### Konektor w claude.ai na nagłówek

claude.ai → Ustawienia → Konektory → Chilli → edycja (albo usuń i dodaj od nowa):

- adres: `https://chilli.example.com/mcp`
- nagłówek: `Authorization` = `Bearer <MCP_SECRET>` (sekret z `grep '^MCP_SECRET=' /opt/chilli/.env`)

Sprawdź w rozmowie („Poszukaj w Chilli, co zapisałem o Anthropic"). Jeśli konektor był usuwany
i dodany od nowa, sprawdź też, czy zaplanowane zadanie „Chilli — tygodniowe podsumowanie znalezisk”
nadal ma go włączonego. Poczekaj na poniedziałkowe podsumowanie. Dopiero gdy oba działają, wyłącz stary adres:

```bash
echo 'MCP_SECRET_IN_URL=false' >> .env && docker compose up -d
```

Test z serwera przez nagłówek (sekret nie pojawia się na ekranie):

```bash
SECRET=$(grep '^MCP_SECRET=' .env | cut -d= -f2)
curl -s -H "Authorization: Bearer $SECRET" -H "Accept: application/json, text/event-stream" \
  -H "Content-Type: application/json" https://chilli.example.com/mcp \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | head -c 200; echo
```

### Eksport

```bash
docker compose exec -T api python -m app.export > /root/chilli-eksport.zip
```

### Kopia zapasowa

Pierwsze uruchomienie ręcznie:

```bash
bash deploy/backup.sh
```

Codziennie o 3:15 (cron roota):

```bash
(crontab -l 2>/dev/null; echo '15 3 * * * cd /opt/chilli && bash deploy/backup.sh >> /var/log/chilli-backup.log 2>&1') | crontab -
```

Wysyłka poza serwer: w `.env` dopisz `BACKUP_REMOTE=<użytkownik>@<host>:<katalog>` i, jeśli serwer
SSH ma inny port, `BACKUP_SSH_PORT` (np. 23 u niektórych dostawców storage box). Serwer musi mieć klucz SSH
dodany po drugiej stronie. Miejsce docelowe czeka na decyzję Pawła.

### Odtworzenie z kopii

```bash
docker compose exec -T db pg_restore -U chilli -d chilli --clean --if-exists < /opt/chilli-backups/db-<data>.dump
docker compose exec -T api tar -C /data -xzf - < /opt/chilli-backups/images-<data>.tar.gz
```

## Czego testy nie sprawdziły

- Czy konektor w claude.ai wysyła nagłówek `Authorization` i jak reaguje na 401. Na wszelki wypadek
  stary adres zostaje włączony, dopóki tego nie potwierdzisz.
- `deploy/backup.sh` (tylko `bash -n`): pg_dump, tar w kontenerze, cron, rsync.
- `apply_schema` na prawdziwej bazie w Dockerze (test robi to samo na lokalnym Postgresie 16).
- Progi łączenia duplikatów sprawdzone na 14 zapisach. Za mało, żeby wykluczyć pomyłki: obserwuj
  pierwsze tygodnie i w razie złego połączenia cofnij je zapytaniem wyżej.
- Zrzut z zrzutem tego samego wpisu (bez linku) nie jest łączony; to poza zakresem etapu.
