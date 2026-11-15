# Katalog i sesja — etap implementatora 2026-11-15

To częściowy checkpoint, nie odbiór ani opis wdrożenia. Sesja serwera i cookie
mają wspólne 7 dni; RAM, logout i zabezpieczenia cookie pozostają bez zmian.

## Dowody i granice

Nowy test `tests/test_catalog_source_session.py` przechodzi przez adapter Telegram,
agregację trzech zdjęć z podpisem, deduplikację części albumu, HTTP, kolejkę,
dispatcher, prawdziwy agent i narzędzia, SQLite oraz dostawę Telegrama.
Provider jest skryptowany, obrazy i dane fikcyjne; test nie dowodzi rozpoznawania
etykiet ani przyczyny zgłoszonego błędu produkcyjnego.

Pierwszy RED: 4 failed / 2 passed. Opis albumu bez szkicu, potem tekst
„zapisz do katalogu” w WWW lub Telegramie: brak produktu, narzędzie odrzuca
`own_label` bez obrazu w bieżącym zdarzeniu. Świeży album z „dodaj do katalogu”
tworzy jeden szkic, pokazuje podgląd i dostarcza odpowiedź. Zasymulowana awaria
po zapisie zachowuje szkic i raportuje go bez ponawiania. Awaria przed pierwszym
narzędziem ujawnia ogólny komunikat o zerze operacji posiłków — osobny RED
raportowania, nie dowód przyczyny produkcyjnego wyjątku.

Test sesji był RED przy cookie 43200 s. Po zmianie: 24 PASS (granica 604800 s
przez HTTP z ręcznie wysłanym także wygasłym cookie, logout, Secure oraz istniejące
rozmowy katalogowe). Trzy RED katalogu pozostają celowo niezamknięte w WIP.

## Następny pionowy etap — projekt, jeszcze bez implementacji

Wzorzec: `tools/diet.py`, `_mutate` / `_perform`: model interpretuje zwykły język,
backend wyprowadza właściciela i request z kontekstu, waliduje, wiąże fingerprint,
wykonuje transakcję i zwraca rzeczywisty wynik. Nie rozszerzać regexów
`product_review.intent`; obecne przechwytywanie przed modelem i unieważnianie
`direct` w `agent.run_agent` trzeba zastąpić spójną ścieżką narzędzi.

1. Zachować lokalnie odczytane pola i powiązanie z faktycznym zdarzeniem źródłowym
   przed powstaniem szkicu. Rozwiązywać jednoznaczne, świeże źródło właściciela
   także między kanałami; odrzucać foreign/local-only/stale, pytać przy wielu
   źródłach lub niezwiązanej rozmowie. Samo „ostatnie zdjęcie” jest niewystarczające.
   Historyczne obrazy nie mogą wracać do zewnętrznego modelu. Nie zmieniać
   `own_label` na `manual` ani pozwalać modelowi wybierać dowolnego event ID.
2. Udostępnić modelowi operacje kontroli/zmiany/zatwierdzenia/anulowania na wzór
   posiłków. Backend wiąże zgodę z podglądem aktualnej wersji faktycznie zapisanym
   w tym kanale, właścicielem i odrębnym późniejszym zdarzeniem użytkownika.
   Model nie może zatwierdzić nowej lub niewidzianej wersji w tym samym obrocie.
   Korekta i zgoda razem tworzą nowy podgląd. Idempotencja i audit w transakcji.
3. Oddzielić request tworzenia od źródłowego eventu zdjęć. Obecne
   `known_outcome` łączy produkt ze źródłowym requestem; po opóźnionym zapisie
   to nie będzie request mutacji. Trwały wynik katalogowy musi wiązać oba,
   obejmować tworzenie/zmianę/zgodę i służyć recovery bez ponowienia narzędzi.
   Przed pierwszym narzędziem nie znać zamiaru z samego wyniku modelu: raportować
   bezpieczny zakres wiedzy o zapisie, nie sugerować, że ledger posiłków dowodzi
   braku operacji katalogowych. Bez nowej bramki słów kluczowych.
4. Dodać do istniejącego promptu heurystykę etykieta/makra/kod/opakowanie → zwykle
   katalog, talerz/porcja → zwykle posiłek; tekst jawny ma pierwszeństwo, wszystkie
   zdjęcia rozpatruj łącznie, opakowanie nie dowodzi spożycia. Niejasność wymaga
   pytania. Przetestować także opakowanie z jawnym spożyciem i talerz z poleceniem
   katalogowym; to wskazówki dla modelu, nie sztywne routowanie.

Następne testy: delayed RED→GREEN, brak ponownego wysyłania obrazów, foreign,
niejednoznaczność, przeterminowanie, replay, naturalna zgoda/korekta przez model
i narzędzia oraz odmowa zgody na niewidzianą wersję w innym kanale.
Nie wyłączać obecnych testów właściciela, wersji, prywatności ani UI.

Nie udało się odtworzyć produkcyjnego wyjątku świeżego albumu. Jedyny proponowany
pakiet diagnostyczny: identyfikator korelacji żądania/zadania, etap awarii,
klasa/kod wyjątku oraz nazwy plików/funkcji i numery linii stosu (bez treści linii).
Bez promptów, zdjęć, tokenów, treści bazy i bez ponawiania próby przez właściciela.
Nie pobierano diagnostyki produkcyjnej.

Pozostają implementacja katalogu, pełna regresja na końcowym SHA, niezależny
review, CI/build/smoke bez publikacji i ewentualny PR. Żadnej z tych bramek nie
uznajemy tutaj za zaliczoną.
