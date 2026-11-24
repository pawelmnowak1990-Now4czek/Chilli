# Krok 3: Skrót „Chilli: zrzut" pod Action Button

Telefon nie ma żadnej logiki: Skrót robi zrzut, wysyła go na `/capture` i pokazuje wynik.
Po stronie serwera nic się nie zmienia, endpoint jest gotowy od kroku 2.

## Budowa Skrótu (aplikacja Skróty na iPhonie)

1. Nowy skrót (+), nazwa: **Chilli: zrzut**.
2. Akcja **Zrób zrzut ekranu** (Take Screenshot).
3. Akcja **Pobierz zawartość URL** (Get Contents of URL):
   - URL: `https://chilli.example.com/capture`
   - rozwiń strzałką „Pokaż więcej":
   - Metoda: **POST**
   - Nagłówki: dodaj nagłówek, klucz `Authorization`, wartość `Bearer ` + token
     (słowo Bearer, spacja, potem `CAPTURE_TOKEN` z menedżera haseł; bez cudzysłowów).
   - Treść żądania: **Formularz** (Form). Dodaj pole typu **Plik**, klucz `image`,
     wartość: zmienna **Zrzut ekranu** (wynik akcji z punktu 2).
4. Akcja **Jeśli** (If): wejście = **Zawartość URL**, warunek **zawiera**, tekst `przyjęty`.
   - w gałęzi „Jeśli": akcja **Pokaż powiadomienie**, tekst `Zapisane w Chilli`.
   - w gałęzi „W przeciwnym razie": akcja **Pokaż alert** z **Zawartością URL**
     (zobaczysz komunikat serwera, np. `brak tokenu` albo `zły token`).

Skróty nie przerywają działania przy kodzie błędu HTTP, tylko zwracają treść odpowiedzi,
dlatego sprawdzamy słowo `przyjęty` z odpowiedzi `202 {"id": "...", "status": "przyjęty"}`.

## Podpięcie pod przycisk

- iPhone z Action Button: Ustawienia → Przycisk Czynności → przewiń do **Skrót** → wybierz **Chilli: zrzut**.
- Bez Action Button: Ustawienia → Dostępność → Dotyk → Stuknięcie w tył → Stuknij dwukrotnie → **Chilli: zrzut**.

Przy pierwszym uruchomieniu iOS zapyta, czy Skrót może łączyć się z `chilli.example.com`. Wybierz **Zawsze zezwalaj**,
inaczej pytanie wróci przy każdym zapisie.

## Bezpieczeństwo

Token jest wpisany w Skrót na stałe. Nie udostępniaj tego Skrótu nikomu (eksport Skrótu zawiera token).
Gdyby wyciekł: nowy `openssl rand -hex 32` w `.env` na serwerze, `docker compose up -d`, nowy token w Skrócie.

## Sprawdzenie na serwerze

```bash
cd /opt/chilli
docker compose exec db psql -U chilli -d chilli \
  -c "SELECT id, created_at, source_type, image_path, processed_at FROM saves ORDER BY created_at DESC LIMIT 5"
docker compose exec api ls -la /data/images/incoming
```

Powinien być wiersz `screenshot` i plik `<id>.png` o rozmiarze kilku MB.

Jeśli coś pada, logi serwisu (bez tokenu, uvicorn loguje tylko ścieżkę i kod):

```bash
docker compose logs --tail 20 api
```

## Pułapki z pierwszego testu (19.11.2026)

- **400 Bad Request od nginx** (strona z napisem nginx, w access.log `"POST /capture HTTP/1.1" 400 166`): niewidoczny znak
  (nowa linia) w wartości nagłówka po wklejeniu tokenu z terminala. Lekarstwo: usunąć nagłówek i dodać od nowa,
  klucz wpisać ręcznie, token wkleić i sprawdzić backspace'em koniec. Token bierz poleceniem
  `grep '^CAPTURE_TOKEN=' /opt/chilli/.env | cut -d= -f2`.
- **„Nie można przeprowadzić konwersji z typu Słownik na typ URL"** w akcji Jeśli: serwer odpowiedział poprawnie (JSON),
  ale zmienna Zawartość URL miała ustawiony zły typ. Stuknij zmienną w Jeśli → Typ → **Tekst**.
- Przy wyborze zmiennej w polu `image` widać tylko Schowek, Bieżącą datę itd.: brakuje bloku „Zrób zrzut ekranu"
  nad „Pobierz zawartość URL". Nie używaj „Dane wejściowe skrótu", przy Action Button są puste.
- W Jeśli warunek ma być **zawiera**, nie „to" (równa się).

Pierwszy zrzut z iPhone'a doszedł 19.11.2026 21:03 UTC jako `image/png` (wiersz `screenshot`).

## Czego nie wiemy przed testem

- Jaki `Content-Type` Skróty nadają plikowi zrzutu. Serwis przyjmuje `image/png`, `image/jpeg`, `image/heic`,
  a dla ogólnego `application/octet-stream` rozpoznaje PNG i JPEG po bajtach. Gdyby i tak wyszło 415, w alercie
  będzie `to nie jest obsługiwany obraz` i dopiszemy obsługę.
- Ile trwa wysyłka zrzutu przez sieć komórkową (zwykle 2-6 MB).
