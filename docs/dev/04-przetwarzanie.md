# Krok 4: przetwarzanie zrzutów

Co powstało:

- `app/processing.py`: po odpowiedzi `/capture` zrzut idzie do przetwarzania w tle (telefon nie czeka).
  Przy starcie serwisu dokańczane są zaległe zrzuty (np. przyjęte w trakcie restartu).
- `app/images.py`: kopia na stałe w `/data/images/<id>.webp`, dłuższy bok max 1568 px. Oryginał z `incoming/` jest usuwany po udanym przetworzeniu.
- `app/vision.py`: Claude czyta kopię i zwraca JSON (structured outputs): `title`, `summary`, `kind`, `tags`, `source_app`, `url`, `content_text`.
  Model z `VISION_MODEL` (pusty = `claude-sonnet-5-5`), effort z `VISION_EFFORT` (domyślnie `low`).
  Włączony serwerowy fallback: gdy model odmówi, API samo ponawia na innym modelu.
- `app/embeddings.py`: wektor 384 liczb z `multilingual-e5-small` w wersji skwantyzowanej (fastembed, ONNX, bez PyTorcha).
  Model jest pobierany przy budowie obrazu Dockera (`Dockerfile`), a nie przy starcie.
- Linki (`source_type = 'link'`) są pomijane, obsłuży je krok 5.

## Błędy i ponawianie

Gdy coś padnie (brak klucza API, sieć, odmowa modelu), błąd trafia do kolumny `error`,
`processed_at` zostaje puste, a oryginał zostaje w `incoming/`. Takie wiersze nie są ponawiane
automatycznie (żeby nie płacić w kółko za ten sam zrzut). Ręczne ponowienie po naprawie przyczyny:

```bash
cd /opt/chilli
docker compose exec db psql -U chilli -d chilli -c "UPDATE saves SET error = NULL WHERE error IS NOT NULL AND source_type = 'screenshot'"
docker compose restart api      # przy starcie serwis przetworzy zaległe
```

## Koszt i pamięć

- Claude: zrzut po zmniejszeniu to ok. 1,5 tys. tokenów wejścia plus ok. 1 tys. tokenów odpowiedzi.
  Na `claude-sonnet-5-5` ($2 / $10 za 1 mln) to szacunkowo ok. 1-1,5 centa za zrzut (niezmierzone, sprawdź w konsoli Anthropic po kilku dniach).
  Inne opcje w `VISION_MODEL`: `claude-opus-5-5` ($4 / $20), `claude-haiku-5-5` ($0,10 / $0,50); jakości odczytu na naszych zrzutach nie porównywaliśmy.
- Embeddingi: na Macu proces z modelem zajmował ok. 650 MB (wersja pełna: 1,9 GB). Na serwerze sprawdź `docker stats --no-stream`.

## Na serwerze

Wymaga `ANTHROPIC_API_KEY` w `/opt/chilli/.env` (patrz rozmowa przy kroku 4 lub `docs/dev/wdrozenie.md`).

```bash
cd /opt/chilli
git pull
docker compose up -d --build        # pierwsza budowa pobiera model, potrwa kilka minut
docker compose logs --tail 20 api
```

Potem zrzut z Action Button i po kilkunastu sekundach:

```bash
docker compose exec db psql -U chilli -d chilli -c "SELECT created_at, title, kind, tags, source_app, processed_at, error FROM saves ORDER BY created_at DESC LIMIT 3"
docker stats --no-stream
```

Zaległy testowy zrzut z kroku 3 zostanie przetworzony sam przy starcie serwisu.

## Wynik wdrożenia (19.11.2026)

Dwa zrzuty z kroku 3 przetworzone przy starcie serwisu: tytuł, typ, tagi i aplikacja poprawne
(`claude-sonnet-5-5`). Właściciel porównał `content_text` z ekranem: tekst się zgadza przy 1568 px. Pamięć po starcie: api 555 MiB, db 27 MiB, łącznie ok. 580 MiB, w budżecie 1-1,5 GB.

## Czego testy nie sprawdziły

- Czy 1568 px (`IMAGE_MAX_SIDE`) wystarcza do odczytu drobnego tekstu: porównaj `content_text` pierwszych zapisów z tym, co było na ekranie.
  Oryginały są usuwane, więc rozdzielczość każdej kopii jest na stałe.
- Zrzutów HEIC: Pillow ich nie otwiera bez dodatkowej biblioteki; zrzuty ekranu z iPhone'a to PNG, więc to nie blokuje.
