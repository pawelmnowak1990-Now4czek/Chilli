# Krok 2: POST /capture

Co powstało:

- `app/capture.py`: endpoint `POST /capture`. Dwa kształty żądania pod jednym adresem:
  - formularz multipart z polem `image` (zrzut ekranu) -> wiersz z `source_type = 'screenshot'`,
  - JSON `{"url": "https://..."}` (link z arkusza udostępniania) -> `source_type = 'link'`.
- `app/auth.py`: token w nagłówku `Authorization: Bearer <CAPTURE_TOKEN>`, porównanie w stałym czasie.
  Pusty `CAPTURE_TOKEN` w `.env` = serwis odrzuca wszystko (503), zamiast wpuszczać każdego.
- `app/storage.py`: obraz ląduje w `/data/images/incoming/<id>.<rozszerzenie>` (wolumen `images`).
  Nazwa pliku to id wiersza, nazwa od klienta nie trafia na dysk.
- `app/saves.py`: jawny `INSERT` do `saves`.
- Nowe ustawienie `MAX_UPLOAD_MB` (domyślnie 15). nginx przepuszcza do 25 MB.

Odpowiedź przychodzi od razu: `202 {"id": "...", "status": "przyjęty"}`. Nic nie jest jeszcze
analizowane, wiersz ma `processed_at = NULL`. Odczyt treści przez Claude i pomniejszenie obrazu
(z usunięciem oryginału z `incoming/`) to krok 4.

Kody błędów: 401 brak lub zły token, 413 obraz za duży, 415 to nie obraz albo zły typ treści,
422 brak pola `image`/`url` albo niepoprawny adres, 503 brak tokenu w konfiguracji.

## Na serwerze

Po aktualizacji kodu (`git pull && docker compose up -d --build`):

```bash
cd /opt/chilli
TOKEN=$(grep '^CAPTURE_TOKEN=' .env | cut -d= -f2)

# link
curl -s -X POST https://chilli.example.com/capture \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'

# obraz (dowolny PNG z serwera albo wgrany przez scp)
curl -s -X POST https://chilli.example.com/capture \
  -H "Authorization: Bearer $TOKEN" -F "image=@/sciezka/do/zrzut.png"

# bez tokenu ma być 401
curl -s -o /dev/null -w '%{http_code}\n' -X POST https://chilli.example.com/capture \
  -H "Content-Type: application/json" -d '{"url": "https://example.com"}'

# co jest w bazie
docker compose exec db psql -U chilli -d chilli \
  -c "SELECT id, created_at, source_type, url, image_path, processed_at FROM saves ORDER BY created_at DESC LIMIT 5"
```

Token czytamy z `.env` do zmiennej, żeby nie wpisywać go ręcznie i nie zostawiać w historii powłoki.
Po testach możesz usunąć testowe wiersze: `DELETE FROM saves WHERE url = 'https://example.com/';`
(z ukośnikiem na końcu: walidacja adresu dopisuje go do samej domeny).
(pliki z `incoming/` po testowych obrazach usuń ręcznie: `docker compose exec api ls /data/images/incoming`).

## Czego testy nie sprawdziły

- Prawdziwego Skrótu z iPhone'a (krok 3): jaki dokładnie `Content-Type` wysyła dla zrzutu.
  Serwis rozpoznaje PNG i JPEG także po bajtach, gdyby Skrót wysłał ogólne `application/octet-stream`.
- Działania za nginx i na Dockerze (na Macu nie ma ani jednego, ani drugiego).
