# Etap 2 roadmapy: rozszerzenie Chrome

Zakres z roadmapy (https://claude.ai/artifact/JuPizpTytFzMQtoE9YYPki, „Etap 2"): mały dodatek do Chrome
(Manifest V3), który wysyła bieżącą stronę, zaznaczony tekst albo zrzut widocznej części karty
na istniejący `POST /capture`. Działa na obecnym tokenie (`CAPTURE_TOKEN`); logowanie dojdzie w etapie 3.

Co powstało:

- `extension/`: rozszerzenie (bez kroku budowania, zwykłe pliki JS):
  - przycisk na pasku: zapisuje zaznaczony tekst, a gdy nic nie jest zaznaczone, adres strony,
  - prawy przycisk myszy: „Zapisz stronę”, „Zapisz link” (na linku), „Zapisz zaznaczenie”, „Zapisz zrzut karty”,
  - skrót klawiszowy Alt+Shift+S: zrzut karty (zmiana w `chrome://extensions/shortcuts`),
  - wynik na ikonie: zielone ✓ (znika po 3 s) albo czerwony ! z opisem błędu po najechaniu myszą,
  - opcje: adres serwera i token (zapisane tylko w tej przeglądarce) oraz przycisk „Sprawdź połączenie”.
- Serwer: `/capture` przyjmuje JSON `{"text": "...", "url": "...", "title": "..."}` jako zapis typu `text`.
  Claude opisuje sam fragment, serwer nie pobiera całej strony. Zły adres (np. `chrome://`) jest pomijany,
  tekst i tak się zapisuje.
- Zrzut karty idzie razem z pełnym adresem strony, więc serwer dociąga pełny tekst artykułu
  (tak jak dla zrzutu z iPhone'a z adresem). Link zapisany z rozszerzenia łączy się z takim zrzutem
  przez etap 1 (ten sam adres).

Testy: `.venv/bin/pytest -q` → 89 passed. Do tego przebieg w Chromium (Playwright) na lokalnym serwerze:
zapis strony, zaznaczenia (z podziałem na linie), zrzutu karty i linku, brak tokenu (otwiera opcje),
zły token (czerwony !), „Sprawdź połączenie” w opcjach. Wszystkie cztery zapisy trafiły do bazy.

## Na serwerze

Po merge'u PR do main (etap 2 wymaga nowej wersji serwera dla zaznaczeń):

```bash
cd /opt/chilli && git pull && docker compose up -d --build
```

## Instalacja w Chrome (na Macu)

1. Pobierz repo albo zaktualizuj je (`git pull`) w `~/projects/Chilli`.
2. Chrome → `chrome://extensions` → włącz „Tryb programisty” (prawy górny róg).
3. „Załaduj rozpakowane” → wskaż katalog `~/projects/Chilli/extension`.
4. Przypnij ikonę papryczki (ikona puzzla na pasku → pinezka przy Chilli).
5. Otworzą się opcje (albo: prawy przycisk na ikonie → Opcje). Adres zostaw domyślny, wklej token,
   czyli wartość `CAPTURE_TOKEN` z `/opt/chilli/.env` (ten sam co w Skrótach), „Zapisz”,
   potem „Sprawdź połączenie”. Ma się pokazać „Połączenie i token działają”.

Token odczytasz na serwerze bez wyświetlania reszty pliku: `grep '^CAPTURE_TOKEN=' /opt/chilli/.env`.
Nie wklejaj go do wątku.

Aktualizacja rozszerzenia po zmianach w repo: `git pull`, potem w `chrome://extensions` strzałka
„odśwież” przy Chilli.

Publikacja w Chrome Web Store (5 USD jednorazowo) nie jest potrzebna do własnego użytku.

## Czego testy nie sprawdziły

- Prawdziwych kliknięć w menu pod prawym przyciskiem i w ikonę: test wywoływał te same funkcje
  bezpośrednio. W prawdziwym Chrome dostęp do karty daje kliknięcie (uprawnienie `activeTab`);
  w teście kopia rozszerzenia miała szersze uprawnienia, bo automat nie umie „kliknąć” jak człowiek.
- Działania na prawdziwym serwerze przez HTTPS (test szedł na lokalny serwer po http).
- Stron, do których Chrome nie wpuszcza rozszerzeń (`chrome://`, sklep Chrome, podgląd PDF):
  zrzut i zaznaczenie mogą tam nie działać, zapis strony dostanie błąd 422 dla adresu `chrome://`.
- Długich zaznaczeń: serwer przyjmuje do 200 tys. znaków, Claude dostaje pierwsze 30 tys.
