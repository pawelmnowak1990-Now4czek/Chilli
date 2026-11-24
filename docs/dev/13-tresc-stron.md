# Treść stron: lepsze wyciąganie i kopia strony przy każdym zapisie

Prośba (24.11.2026, pomysły z analizy Karakeep): sprawdzić, czy da się lepiej wyciągać treść
artykułów (Karakeep używa Defuddle), i pilnować, żeby pełny tekst strony zawsze trafiał do bazy.

## Porównanie ekstraktorów

16 adresów, z czego 14 dało się pobrać (spidersweb: 404, Hacker News: 419): wszystkie nie-X adresy
z bazy na serwerze plus typowe artykuły (blogi, Medium, dokumentacja, polskie portale). HTML pobrany
raz z Maca, liczone słowa po zamianie na tekst. Defuddle w Pythonie to
`pydefuddle` 0.1.0 (jedno wydanie, kwiecień 2026); oryginał jest w JavaScripcie, a Node w obrazie
to kolejne setki MB, więc odpadł z góry.

| Strona | trafilatura (Markdown) | pydefuddle |
| --- | --- | --- |
| LinkedIn, post | 390 | 70 |
| pracuj.pl, oferta | 571 | 731 (dodatkowo: baner regulaminu, „przejdź do…”) |
| support.claude.com, artykuł | 1139 | 1208 |
| academy.claude.com | 222 | 0 |
| paulgraham.com | 12298 | 12316 |
| martinfowler.com | 6479 | 6783 |
| simonwillison.net | 904 | 1174 (dodatkowo: lista wpisów z serii, stopka) |
| anthropic.com, artykuł | 2716 | 2751 |
| Medium | 2215 | 2263 |
| bankier.pl | 967 | 1000 |
| blog.cloudflare.com | 2591 | 2598 |
| stripe.com, blog | 2369 | 2399 |

Wniosek: trafilatura zostaje. pydefuddle na dwóch stronach nie dał nic albo prawie nic, a nadwyżka
słów na pozostałych to głównie menu, banery i listy wpisów. readability-lxml wypadł gorzej od obu.

Krótkie zapisy na serwerze nie wynikają z ekstraktora: LinkedIn z Maca daje 3061 znaków (post
z komentarzami), a pobrany z serwera 648 (sam post), bo serwis pokazuje adresowi VPS inną stronę.
pracuj.pl z serwera zaczyna się od komunikatu „nie wspieramy Twojej przeglądarki”; to też
odpowiedź serwisu, nie błąd wyciągania.

## Co się zmieniło

- `app/fetch.py`: tekst artykułu wyciągany jako Markdown (`output_format="markdown"`), więc zostają
  śródtytuły (`##`), punkty listy i tabele, a akapity są rozdzielone pustą linią. trafilatura
  w Markdownie wstawia ukośnik przed `_`, `*`, `[`, `]` i `#` (`ROW\_NUMBER`); usuwamy go, żeby nazwy
  z SQL i kodu dało się wyszukać. Fragmentów kodu w backtickach nie ruszamy (tam `\d+\.` to treść).
- `db/schema.sql` (dopisane): `saves.page_text`, kopia tego, co serwer pobrał spod adresu zapisu.
  - link: ta sama treść co `content_text`,
  - zrzut z pełnym adresem: zawsze, także gdy strona dała tylko skrawek albo opis z meta
    (wtedy `content_text` zostaje z odczytu zrzutu, a skrawek trafia tylko do `page_text`),
  - ponowne przetworzenie, przy którym strona nie odpowiedziała, nie kasuje starej kopii.
  - zaznaczony tekst z przeglądarki: strony dalej nie pobieramy (zapisany ma być fragment).
- `get_save` w MCP zwraca `page_text`, gdy różni się od `content_text`.
- `app/refetch.py`: uzupełnienie kopii dla starych zapisów (linki: kopia w bazie bez sieci,
  zrzuty z adresem: jedno pobranie strony, bez Claude).

Po wdrożeniu:

```
cd /opt/chilli
docker compose exec api python -m app.refetch           # podgląd
docker compose exec api python -m app.refetch --apply
```

Niezrobione: archiwum HTML i zrzuty całych stron (Karakeep stawia do tego Chrome'a, za ciężkie
na ten VPS). Stare linki zostają w starym formacie tekstu, dopóki nie przejdą `app.reprocess`.
