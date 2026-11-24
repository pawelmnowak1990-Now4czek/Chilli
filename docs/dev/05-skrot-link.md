# Krok 5: linki (Skrót w arkuszu udostępniania + pobieranie treści)

## Co robi serwer (app/fetch.py, app/link_analysis.py, app/processing.py)

- Link z udostępniania: pobranie treści -> Claude opisuje (tytuł, streszczenie, typ, tagi, serwis) -> embedding -> baza.
  Pełny tekst (do 200 tys. znaków) trafia do `content_text`; do Claude idzie najwyżej 30 tys. znaków.
- Zwykłe strony: HTML -> tekst artykułu przez `trafilatura` (bez menu i stopek).
- Posty z X: `api.fxtwitter.com` (pełny tekst, także długich postów; adres posta trafia do tego serwisu),
  a gdy nie działa, oficjalny oEmbed X (tylko początek długiego posta).
- Zrzut z Action Button z adresem strony. Uwaga (sprawdzone 20.11.2026): iOS przez „Pobierz Adresy URL z ekranu" podaje
  w Safari tylko domenę, nie adres podstrony; samej domeny serwer nie pobiera (zostaje tekst ze zrzutu). Dokładny link daje tylko udostępnianie.
  Gdy przyjdzie pełny adres:
  opis ze zrzutu, ale `content_text` = pełny tekst strony. Gdy pobranie się nie uda, zostaje tekst ze zrzutu.
- Gdy link nie da się pobrać (404, blokada, brak tekstu), błąd trafia do `error` (ponawianie: docs/dev/04-przetwarzanie.md).

Sprawdzone na żywo z Maca 20.11.2026: post z X (8791 znaków przez fxtwitter) i artykuł support.claude.com (6925 znaków).

## Budowa Skrótu

1. Skróty → przytrzymaj „Chilli-zrzut" → Duplikuj → nazwa **Chilli: link** (nagłówek z tokenem przechodzi z kopią).
2. Usuń blok „Zrób zrzut ekranu".
3. Ikona (i) → włącz **Pokaż w arkuszu udostępniania**; w „Odbieraj … z Arkusza udostępniania" zaznacz **wszystkie typy**
   (sam URL nie wystarcza dla X: Skrót dostawał puste wejście i serwer zwracał 422 `input is empty`),
   a „Jeśli brak danych wejściowych" ustaw na **Zatrzymaj**.
4. W „Pobierz zawartość URL": Treść żądania **JSON**, usuń pole `image`, dodaj pole typu **Tekst**: klucz `url`, wartość „Dane wejściowe skrótu".
5. „Jeśli Zawartość URL (typ Tekst) zawiera przyjęty" i powiadomienie bez zmian.

Test: Safari → Udostępnij → Chilli: link. Gdy Skrótu nie ma na liście: „Edytuj czynności" na dole arkusza.

## Sprawdzenie na serwerze

```bash
cd /opt/chilli
docker compose exec db psql -U chilli -d chilli -c "SELECT created_at, source_type, url FROM saves WHERE source_type = 'link' ORDER BY created_at DESC LIMIT 3"
```

W X udostępniaj przez „Udostępnij przez…" (systemowy arkusz). Serwer wyciąga pierwszy adres `https://…` także z tekstu z dopiskiem.
Działa od 19.11.2026 22:36 UTC (link z X zapisany).

Wdrożone 20.11.2026 07:10 UTC: trzy zaległe linki przetworzone (X 8791 znaków, Claude Help Center 6925, LinkedIn 648 - LinkedIn bez logowania pokazuje tylko część posta).
