# Uzgodnione poprawki po odświeżeniu kontenera

Decyzje właściciela: 2026-10-29. Dokument zakresu; nie potwierdza implementacji ani testów.

## Jeden PR: przegląd, posiłki, katalog i wykresy

Dopuszczalne osobne commity w jednym PR. Bez automatycznego merge lub wdrożenia.

- Dzisiejsze kalorie spoczynkowe: średnia z ostatnich 7 dni, zaokrąglenie do pełnych 100 kcal, prefiks `~`. Bez dodatkowych opisów. Dni zakończone: faktyczne dane Garmin. Zatwierdzone: 7 poprzednich dni kalendarzowych, bez dzisiaj; średnia z dostępnych pomiarów, bez wstawiania zer w brakujące dni. Brak wszystkich pomiarów oznacza brak danych.
- Posiłki we wszystkich widokach: najnowsze na górze, data i godzina malejąco. Propozycja: brak godziny na końcu danego dnia i stabilne rozstrzygnięcie remisów.
- Akcje posiłków: małe estetyczne ikony edycji/usunięcia, dostępne etykiety i potwierdzenie usuwania.
- Wykresy: bez dodawania biblioteki. Łączyć dostępne punkty przez luki, zachować rzeczywisty odstęp czasu, nie dopisywać pomiarów. Wartość/data/jednostka po najechaniu; obsługa dotyku.
- Omów: kompaktowa akcja AI. Obok link Garmin Connect do odpowiedniej kategorii/rekordu, jeśli istnieje. Zweryfikować URL; właściciel może je podać.
- Katalog: zbadać i naprawić `owner or version mismatch; preview required` przy edycji rozmiaru sztuki bez obchodzenia kontroli wersji/właściciela. Formularz zamykalny również po błędzie. Zwarta lista i małe ikony akcji.

## Osobny temat / PR: diagnostyka — niski priorytet

Cel: wyjaśniać czas konkretnego requestu użytkownika (np. „dodaj posiłek”), a nie eksponować techniczne zadania tła. Pokazać gdzie upłynął czas: pętle, wywołania pamięci, oczekiwanie na LLM, pobieranie Garmin. Dodać zużycie tokenów per request (wejście/wyjście, cache jeśli dostawca raportuje), najlepiej jako dyskretne rozwijane szczegóły przy odpowiedzi w rozmowie; brak raportowania nie może udawać zera. Tokeny i czas widoczne w rozmowie to propozycja UX do dopracowania w osobnym temacie. Prosta oś czasu/waterfall mile widziana, bez rozbudowy dla samej rozbudowy. Aktualnie aplikacja działa dość płynnie; odłożyć do ważniejszej potrzeby. Oddzielić „nie dotyczy” od rzeczywiście brakującego pomiaru.

## Osobny temat: porządki w data

Zachować w backlogu. Najpierw inwentaryzacja zależności plików i sprawdzenie produkcyjnej migracji do SQLite. Dokumenty pacjenta mają źródło prawdy i rewizje w SQLite; stare MD są wejściami importu brakujących dokumentów. `system_prompt.md` pozostaje plikowym override. CSV znaleziono w migratorze, ale pełny audyt wciąż wymagany. Nie usuwać hurtowo plików. Preferować archiwizację po weryfikacji; eksport bieżących dokumentów wykonywać z SQLite, nie ze starych MD.
