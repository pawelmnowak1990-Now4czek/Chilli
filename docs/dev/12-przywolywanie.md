# Przywoływanie: „Z archiwum" i przypomnienia

Prośba (24.11.2026, pomysły z analizy Recall/Readwise/Raindrop): Chilli ma samo podsuwać
zapomniane zapisy w porannym przeglądzie i przypominać o konkretnym zapisie w wybranym dniu.

Co powstało:

- `db/schema.sql` (dopisane): `saves.remind_at` (data, nie godzina) i indeks częściowy.
- `app/recall.py`:
  - `from_archive`: zapisy sprzed 14–56 dni, ze statusem `nowy`, z oceną 7+ w aktywnym projekcie,
    bez schowanych duplikatów. Kolejność po `md5(id || data)`: tego samego dnia te same zapisy,
    następnego inne, bez zapamiętywania w bazie, co już było.
  - `set_reminder`: termin = dzisiejsza data w Warszawie + N dni. Liczymy po dacie, żeby
    przypomnienie ustawione wieczorem trafiło do porannego przeglądu właściwego dnia.
    `days = 0` kasuje przypomnienie.
  - `due_reminders`: zapisy z terminem dziś albo wcześniej. Zostają na liście, dopóki właściciel
    nie zareaguje: `set_status` czyści `remind_at`, gdy termin już minął, albo zawsze przy
    `wykorzystany` i `archiwum`. Przypomnienie na przyszłość przeżywa zwykłe `przejrzany`, bo AI
    zmienia status przy okazji innych rozmów.
- MCP: `from_archive(limit=2)`, `remind_save(save_id, days=7)`, `due_reminders(limit=20)`;
  `get_save` zwraca też `remind_at`.

Codzienne podsumowanie (zadanie w claude.ai) woła `from_archive` i `due_reminders` i pokazuje
je w osobnych sekcjach. Zadanie zmieniamy dopiero po wdrożeniu, bo wcześniej tych narzędzi nie ma.

Uwaga: dane na serwerze zaczynają się 19.11.2026, więc „Z archiwum" będzie puste mniej więcej
do 3.12.2026. To nie błąd.
