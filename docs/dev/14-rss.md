# Subskrypcje RSS oceniane względem projektów

Prośba (24.11.2026, pomysł z analizy Karakeep): kanały RSS jako źródło, ale do porannego przeglądu
trafiają tylko wpisy z oceną 7+ dla projektów właściciela.

Co powstało:

- `db/schema.sql` (dopisane): `feeds` (adres, tytuł, `active`, ostatnie pobranie i błąd)
  i `feed_entries` (wpis: adres, tytuł, opis bez HTML-a, ocena, `save_id` po zapisaniu).
  Wpisy celowo nie trafiają do `saves`: tam są tylko rzeczy, które właściciel sam wskazał,
  więc wyszukiwanie, `top_saves` i podsumowanie tygodniowe nie zalewają się blogami.
- `app/feeds.py`:
  - dodanie kanału zapamiętuje jego obecne wpisy, ale ocenia tylko 5 najnowszych,
  - co `FEED_POLL_HOURS` godzin (domyślnie 6, `0` wyłącza) wątek w serwisie pobiera aktywne kanały
    po kolei; nowych wpisów najwyżej 20 na kanał na raz, reszta oznaczona jako widziana,
  - ocena z samego tytułu i opisu z kanału (`app/relevance.py`), bez pobierania strony i bez
    embeddingu. To oszczędza pamięć na VPS i tokeny,
  - zapisanie wpisu tworzy zwykły zapis typu link, przetwarzany jak link z telefonu.
- MCP: `add_feed(url)`, `list_feeds`, `set_feed_active(url, active)`,
  `feed_highlights(days=1, min_score=7, limit=10)`, `save_feed_entry(entry_id)`.

Pamięć: wątek działa w tym samym procesie co serwis (osobny proces ładowałby drugi raz model
embeddingów), a `feedparser` to czysty Python. Dodatkowej pamięci nie mierzyłem; do sprawdzenia
po wdrożeniu przez `docker stats`.

Koszt: każdy nowy wpis to jedno krótkie wywołanie Claude (tytuł, opis, lista projektów).
Przy 10 kanałach po kilka wpisów dziennie to kilkadziesiąt wywołań na dzień.

Jak dodać kanał: w rozmowie z Claude „dodaj do Chilli kanał https://.../feed”. Adres musi być
adresem kanału (RSS albo Atom), nie strony głównej bloga.
