# „Masz już coś o tym" w rozszerzeniu przeglądarki

Prośba (24.11.2026, pomysł z Recall „Augmented Browsing"): rozszerzenie w Dia pokazuje 1–3 zapisy
powiązane z otwartą stroną, żeby zapis wracał we właściwym momencie, a nie raz dziennie.

Co powstało:

- `POST /related` (`app/related.py`), ten sam token co `/capture`. Treść: `{"url": ..., "title": ...}`.
  Odpowiedź:
  - `already_saved`: zapisy tej samej strony (adres po normalizacji z `app/dedupe.py`),
  - `related`: do 3 zapisów bliskich znaczeniem do tytułu strony, bez archiwum i schowanych duplikatów.
  Tylko id, tytuł, adres, data i typ, bez streszczeń i treści: token z rozszerzenia był do tej pory
  tylko do zapisu, a teraz pozwala też poznać tytuły zapisów.
- Próg `RELATED_MAX_DISTANCE` (domyślnie 0,15) w `.env`. Dobrany na 29 zapisach z serwera: tytuł zapisu
  jako zapytanie do embeddingów wszystkich zapisów. Pary o tym samym temacie (SEO z SEO, dwa teksty
  o Anthropic) wychodziły 0,07–0,13, a losowe pary zapisów mają medianę 0,19 i 25. percentyl 0,17.
  Przy 0,15 odpadają luźne skojarzenia typu „ściąga z data science" → „taktyki SEO" (0,164).
  Druga próba z prawdziwymi tytułami stron (`<title>`, z dopiskami typu „| Claude Help Center"):
  strony zapisane w Chilli wychodziły 0,06–0,135 od własnego zapisu, a 8 stron spoza bazy miało
  najbliższy zapis w odległości 0,135–0,215. Pod progiem znalazł się tylko artykuł Anthropic
  o agentach (najbliżej: Claude Academy 0,135, ścieżka FDE 0,146), co ma sens. Gdy podpowiedzi
  będzie za mało, podnieść do 0,17; gdy za dużo przypadkowych, zejść do 0,13.
- Rozszerzenie 0.2.0 (`extension/`):
  - po wejściu na stronę i przełączeniu karty pyta `/related` (wyniki pamięta 10 minut na adres);
    na stronach typu X i LinkedIn reaguje też na zmianę adresu bez przeładowania i późny tytuł,
    a odpowiedź dla strony, z której już wyszedłeś, jest pomijana,
  - czerwony `!` po błędzie zapisu zostaje do przejścia na inną stronę (podpowiedź go nie zakrywa),
  - pomarańczowa liczba na ikonie = ile powiązanych, niebieska kropka = ta strona już jest w Chilli,
    tytuły w podpowiedzi po najechaniu na ikonę,
  - lista z linkami: menu pod prawym przyciskiem „Powiązane zapisy w Chilli" albo Alt+Shift+R,
  - kliknięcie ikony dalej zapisuje jednym ruchem (bez okienka),
  - w opcjach można to wyłączyć; karty incognito i adres własnego serwera są pomijane.
  - nowe uprawnienie `tabs` (adres i tytuł karty bez klikania w rozszerzenie).

Prywatność: adres i tytuł każdej odwiedzanej strony idą na własny serwer Chilli (w treści żądania,
więc nie trafiają do logu nginx). Nigdzie dalej. Embedding liczy lokalny model na serwerze.

Aktualizacja w Dia po wdrożeniu serwera: `git pull` w `~/projects/Chilli`, potem w `dia://extensions`
strzałka odświeżania przy Chilli. Dia zapyta o nowe uprawnienie (dostęp do kart).

Sprawdzone automatycznie: rozszerzenie w Chromium z Playwrighta i atrapą serwera (liczba na ikonie,
podpowiedź, lista z linkami, wyłączenie w opcjach, strona zmieniająca adres przez pushState,
czerwony `!` po przełączeniu kart). Nie sprawdzone: Dia i prawdziwe strony.
