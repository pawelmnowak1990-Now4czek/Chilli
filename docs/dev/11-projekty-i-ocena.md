# Projekty właściciela i ocena przydatności zapisów

Prośba (23.11.2026): przy każdym zapisie Chilli ma podpowiadać, do których projektów właściciela
wpis może się przydać, i oceniać przydatność w skali 1–10. Potem można poprosić o zestawienie
najbardziej przydatnych wpisów.

Co powstało:

- `db/schema.sql` (tylko dopisane):
  - `projects`: nazwa (unikalna), opis, `active`. Lista żyje w bazie, nie w repo.
  - `save_projects`: jedna ocena 1–10 i krótkie uzasadnienie na parę (zapis, projekt).
    Brak wiersza znaczy, że zapis do projektu nie pasuje. Usunięcie zapisu albo projektu kasuje oceny.
  - `saves.rated_at`: kiedy zapis był oceniany. NULL = jeszcze nie oceniony
    (inaczej niż „oceniony, nic nie pasuje", co daje rated_at i zero wierszy w save_projects).
- `app/relevance.py`: osobne, tanie wywołanie Claude po przetworzeniu zapisu. Dostaje tytuł,
  streszczenie, tagi, początek treści i aktywne projekty. Odpowiedź jest porządkowana w Pythonie:
  nieznane projekty odpadają, ocena przycinana do 1–10. Bez aktywnych projektów API nie jest wołane.
- `app/processing.py`: ocena na końcu przetwarzania. Jej błąd nie oznacza zapisu jako błędnego,
  zapis zostaje tylko bez oceny (`rated_at` NULL).
- `app/projects.py`: SQL projektów i ocen, w tym zestawienie najlepszych.
- MCP, nowe narzędzia:
  - `list_projects`: projekty z liczbą pasujących zapisów,
  - `upsert_project(name, description, active)`: dodanie albo zmiana; `active=false` kończy projekt:
    nowe zapisy nie są pod niego oceniane, a `top_saves` bez projektu go pomija. Jego stare oceny
    zostają widoczne przez `top_saves(project=...)`, dopóki `rerate --all` ich nie zastąpi,
  - `top_saves(project, days, min_score, limit)`: od najwyższej oceny. Bez projektu liczy się
    najlepsza ocena zapisu wśród aktywnych projektów. Archiwum i schowane duplikaty pomijane.
  - `get_save` zwraca też `projects` (projekt, ocena, uzasadnienie).
- `app/rerate.py`: ocena starych zapisów; nie rusza tytułu, treści ani embeddingu.

Ocena zależy od opisów projektów, więc opis ma mówić, czego projekt potrzebuje
(np. „gra karciana w epoce napoleońskiej, szukam mechanik i grafik epoki"), a nie tylko co to jest.

Na serwerze, po wdrożeniu (schemat dochodzi sam przy starcie serwisu):

1. Wgrać listę projektów, np. w rozmowie z Claude: „dodaj do Chilli projekt X: opis”.
2. Ocenić stare zapisy:

```
cd /opt/chilli
docker compose exec api python -m app.rerate            # podgląd: ile zapisów, nic nie zapisuje
docker compose exec api python -m app.rerate --apply    # ocena nieocenionych
docker compose exec api python -m app.rerate --all --apply   # ponowna ocena wszystkich
```

Każda ocena to jedno płatne wywołanie Claude na zapis (krótki tekst, bez obrazu).

Niezrobione: nowy projekt nie wywołuje sam ponownej oceny starych zapisów, trzeba puścić
`rerate --all`. Konta wielu użytkowników: tabela `projects` dostanie wtedy właściciela.
