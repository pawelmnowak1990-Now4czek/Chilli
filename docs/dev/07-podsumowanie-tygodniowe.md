# Krok 7: podsumowanie tygodniowe

Bez kodu na serwerze (decyzja z CLAUDE.md): zaplanowane zadanie w claude.ai odpytuje bazę przez konektor MCP „Chilli".

- Zadanie: „Chilli — tygodniowe podsumowanie znalezisk", co poniedziałek 8:51 (Europe/Warsaw), pierwszy raz 23.11.2026.
- Co robi: `list_recent` z 7 dni, łączy duplikaty, grupuje tematycznie, jedno zdanie + link na znalezisko,
  sekcja „Warto wrócić" i krótka statystyka. Tylko odczyt, statusów nie zmienia.
- Utworzone 20.11.2026; w rozmowie zakładającej zadanie Claude miał dostęp do Chilli (`list_recent` zwrócił 11 zapisów).

## Potwierdzone

20.11.2026: ręczne uruchomienie zadania z Scheduled przeszło bez problemów, zaplanowany przebieg widzi konektor Chilli.

## Zmiana treści zadania

claude.ai → Scheduled → „Chilli — tygodniowe podsumowanie znalezisk" → edycja polecenia. Gdyby podsumowanie miało oznaczać
zapisy jako `przejrzany`, trzeba to dopisać wprost (narzędzie `set_status`).
