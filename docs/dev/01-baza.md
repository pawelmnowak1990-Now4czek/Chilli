# Krok 1: baza

Co powstało:

- `db/schema.sql`: tabela `saves` z pgvector (bez zmian poza usunięciem zbędnego `pgcrypto`:
  w Postgresie 16 `gen_random_uuid()` jest wbudowane).
- `app/db.py`: otwieranie połączenia (`db.connect()`) i `db.check()` do sprawdzania, czy baza żyje.
- `/health` pokazuje teraz także stan bazy: `{"status": "ok", "env": "prod", "db": "ok"}`
  albo `"db": "error"`, gdy serwis nie może się połączyć.
- Testy w `tests/test_db.py`: schemat się ładuje, pgvector działa, wektor musi mieć 384 wymiary,
  CHECK-i odrzucają nieznane wartości `source_type`, `status` i `kind`.

## Ważne: schemat ładuje się tylko raz

`db/schema.sql` jest podpięty pod `/docker-entrypoint-initdb.d/`. Postgres uruchamia te pliki
**wyłącznie przy pierwszym starcie z pustym wolumenem** `db_data`. Późniejsze zmiany w pliku
nie trafią same do istniejącej bazy. Dopóki w bazie nie ma nic cennego, najprościej:

```bash
docker compose down -v      # -v kasuje wolumeny, czyli CAŁĄ bazę i obrazy
docker compose up -d --build
```

Gdy będą już prawdziwe zapisy: zmianę robimy osobnym `ALTER TABLE` w psql, a `schema.sql`
aktualizujemy, żeby nowa instalacja dostała ten sam stan.

## Jak uruchomić testy na Macu

Bez Dockera: pakiet `pgserver` instaluje w `.venv` Postgresa 16 z pgvector i stawia go na czas testów.

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt -r requirements-dev.txt
.venv/bin/pytest -q
```

## Na serwerze

Po krokach 1-6 z `docs/dev/wdrozenie.md`:

```bash
cd /opt/chilli
docker compose exec db psql -U chilli -d chilli -c '\d saves'     # struktura tabeli
docker compose exec db psql -U chilli -d chilli -c "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
curl -s http://127.0.0.1:8000/health                               # "db": "ok"
```

Do psql na serwerze wchodzisz tak: `docker compose exec db psql -U chilli -d chilli`
(port bazy nie jest wystawiony na zewnątrz kontenera, i dobrze).
