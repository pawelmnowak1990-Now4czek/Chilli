# Pełna treść artykułów X i linków bez treści

Problem (21.11.2026): link do artykułu X (długi tekst pisany w X, adres posta wskazuje
`x.com/i/article/…`) zapisał się jako sam adres, a Claude opisał go jako „treść niedostępna".
Przyczyna: fxtwitter zwraca cały artykuł w polu `tweet.article` (tytuł i bloki treści),
a `app/fetch.py` czytał tylko `tweet.text`, w którym przy artykule jest sam link.
Pobieranie działało, problemem było odczytanie odpowiedzi.

Co powstało:

- `app/fetch.py`:
  - artykuł X: tytuł i bloki (format edytora Draft.js) zamienione na tekst; nagłówki jako `## `,
    punkty jako `- `, obrazy jako `[Obraz: podpis]`, nieznane typy bloków jako zwykły akapit.
    Gdy autor dopisał coś poza linkiem, ten komentarz zostaje nad artykułem.
  - gdy po pobraniu zostaje sam link albo pusto, `FetchError` zamiast zapisu bez treści.
    Zapis trafia wtedy do kolumny `error` i można go ponowić. Długości nie sprawdzamy,
    bo krótki post to poprawna treść.
  - zwykłe strony: gdy `trafilatura` nic nie znajdzie, druga, luźniejsza próba (`favor_recall`),
    a na końcu opis strony z meta (`og:description`). Taki wynik ma `partial=True`: zrzut z tym
    adresem zostawia wtedy własny tekst, bo jedno zdanie opisu nie może nadpisać pełnego odczytu
    ekranu. Dla stron X innych niż post luźniejszych prób nie ma (bez logowania X pokazuje tylko
    ogólny opis serwisu).
- `app/reprocess.py`: ponowne przetworzenie linków bez treści i linków z błędem.
  Status i notatka zostają.

Na serwerze, po wdrożeniu:

```
cd /opt/chilli
docker compose exec api python -m app.reprocess
docker compose exec api python -m app.reprocess --apply
```

Pierwsza komenda tylko pokazuje kandydatów, druga przetwarza ich jeszcze raz (płatne wywołanie
Claude na każdy zapis).

Niezrobione: linki osadzone w treści artykułu X (encje LINK) są pomijane, zostaje sam tekst.

Poza zakresem: zewnętrzny czytnik stron (np. Firecrawl) jako zapas dla stron, których
`trafilatura` nie umie przeczytać. Wymaga klucza, kosztuje i wysyła adresy do kolejnego serwisu,
więc to osobna decyzja.

Testy: `.venv/bin/pytest -q` → 101 passed (artykuł X z blokami, komentarz autora nad artykułem,
sam link = błąd także gdy fxtwitter nie działa, strona bez artykułu = opis z meta, zrzut nie traci
własnego tekstu przy takim opisie, wybór kandydatów i zachowanie statusu przy
ponownym przetworzeniu). Sprawdzone też na żywym linku z 21.11: 12 439 znaków, tytuł artykułu.
