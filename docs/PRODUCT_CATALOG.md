# Własny katalog żywności

Katalog jest częścią istniejącej aplikacji i jej pojedynczej bazy SQLite.
Własne etykiety i jawne korekty właściciela mają pierwszeństwo. Open Food Facts
(OFF) służy wyłącznie jako zapasowy odczyt po kodzie; nie zapisuje ani nie
nadpisuje własnych produktów.

## Użycie

1. W Rozmowie (WWW lub Telegram) prześlij własne zdjęcie czytelnej etykiety
   i poproś o dodanie produktu do katalogu. Obowiązuje istniejąca osobna zgoda
   `K90_ALLOW_MODEL_IMAGES=true`, walidacja formatu i limit 5 MB. Nie ma nowego
   OCR ani innej usługi modelowej. Zwykłe zdjęcia posiłków zachowują dotychczasową obsługę.
2. Model proponuje **szkic**: nazwa, marka, opcjonalny kod, podstawa 100 g lub
   100 ml, kcal oraz białko/węglowodany/tłuszcz w gramach. Brakujących danych
   nie zastępuje się zerem; nieczytelne pola wymagają doprecyzowania.
3. Sprawdź wszystkie wartości i jednostkę w zakładce **Katalog**, obejrzyj
   źródłową etykietę i ewentualnie użyj **Popraw**. Można też dodać produkt
   ręcznie, bez zdjęcia i bez dostępu do sieci. Przecinek dziesiętny jest obsługiwany.
4. Zatwierdź przyciskiem konkretnej wersji lub dokładną komendą
   `/produkt zatwierdz ID WERSJA`. Samo „potwierdzono” w odpowiedzi modelu nie
   zatwierdza produktu. Zmiana szkicu unieważnia wcześniejszy numer wersji.
   Korekty zapisują nowy szkic; wymagają ponownego sprawdzenia.
5. **Zapisz porcję** przy potwierdzonym produkcie wymaga dodatniej ilości g albo ml
   zgodnej z podstawą. Agent wyszukuje produkty i zapisuje cały logiczny posiłek przez `log_meal`.
   Przeliczanie wykonuje kod: 64 kcal/B12/W4,1/T0 na100g → dla150g
   96 kcal/B18/W6,15/T0. Nie ma domyślnej gęstości ani zamiany g↔ml.

Panelowa porcja trafia atomowo do istniejących posiłków i zachowuje pełny snapshot
produktu, wersji, wartości na100 oraz ilości i wyniku. Późniejsze zmiany katalogu
nie przeliczają dawnych posiłków. Klucz formularza chroni ponowienie tej samej
operacji; nowy klucz oznacza nowy posiłek. Porcje panelowe są zapisywane z bieżącą
datą/czasem aplikacji. Chat używa kompletnego `log_meal` opisanego poniżej;
nie zapisuje już osobnych porcji każdego składnika. Nowe wiadomości nie są
porównywane po podobieństwie jako duplikaty spożycia.

Kody są tekstem GTIN8/12/13/14 z kontrolą cyfry kontrolnej. Zera początkowe są
istotne; spacje, URL i niepoprawne kody są odrzucane, a nie naprawiane po cichu.
Ten sam kod nie może należeć do dwóch własnych wpisów. Wpisy bez kodu są
obsługiwane; ponowienie tego samego formularza używa stałego klucza żądania.
Wyszukiwanie lokalne zwraca maksymalnie30 wyników i obsługuje polskie litery.

## Zapasowy odczyt OFF i pochodzenie

**Sprawdź kod** i narzędzie `lookup_food_barcode` najpierw sprawdzają dokładny
kod lokalny. Zwracają także lokalny szkic zamiast zastępować go danymi z sieci.
Zewnętrzny wynik ma stan `unverified`, pochodzenie `openfoodfacts`, atrybucję
oraz adres źródła i licencji. Nie jest produktem do zapisu porcji ani własną
etykietą. Nie ma automatycznego importu ani uploadu zdjęć/poprawek/katalogu.
Po samodzielnym sprawdzeniu etykiety właściciel może wprowadzić własne wartości.

Adapter używa wyłącznie HTTPS `world.openfoodfacts.org/api/v3/product/CODE`,
bez przekierowań i proxy ze środowiska. Żąda odpowiedzi bez kompresji i odrzuca
inne Content-Encoding przed odczytem strumienia. Wysyła kod, listę niezbędnych pól
publicznych i własny User-Agent. Cache jest oddzielny od własnych rekordów,
ważny24h. Trwały limit lokalny to co najmniej10s pomiędzy próbami (6/min),
a429 respektuje Retry-After (sekundy; inne formaty konserwatywnie1h).
Brak automatycznych retry. Timeout connect/read3s/5s, limit odczytu262144B,
kontrola czasu między porcjami12s, głębokość JSON16. Limit czasu odczytu
pojedynczej porcji zależy także od biblioteki HTTP. Błędy/awaria sieci pozostawiają
lokalny katalog dostępny.

Wymagane są oznaczenie rynku `en:poland`, zgodny kod i komplet kcal/B/W/T.
Nie są to dowody poprawności etykiety. Null nie jest zerem; zero tłuszczu jest
poprawne. kJ jest jawnie przeliczane przez4,184 tylko przy braku kcal.
Wartość energii po przeliczeniu musi mieścić się w zakresie0–1000kcal na100;
nierealny wynik jest odrzucany przed zapisem cache, tak samo jak błędne makro.
Dla legacy nutriments z podstawą100ml wymagane jest dodatkowo jawne
`product_quantity_unit=ml`; niejednoznaczne rekordy są odrzucane. Adapter nie
próbuje zgadywać kategorii ani poprawiać podejrzanego produktu.

[Oficjalny indeks API](https://github.com/openfoodfacts/openfoodfacts-server/blob/main/docs/api/index.md)
rekomenduje v3 (obecnie3.6); [surowa specyfikacja v3](https://github.com/openfoodfacts/openfoodfacts-server/blob/main/docs/api/ref/api-v3.yaml)
ma starszy nagłówek3.4. Zaimplementowany odczyt v3 sprawdzono publicznym GET,
nie założeniem o strukturze v2. Oficjalny limit odczytu produktów to15/min/IP;
inne aplikacje z tego samego IP współdzielą ten limit.

Dane OFF: **Open Food Facts, ODbL1.0**, zawartość **Database Contents License1.0**;
[oficjalne zasady licencji](https://github.com/openfoodfacts/openfoodfacts-server/blob/main/docs/api/tutorials/license-be-on-the-legal-side.md).
Zdjęcia OFF nie są pobierane. Funkcja nie realizuje redystrybucji zbiorczej.
Nie oznacza to deklaracji, że prywatny własny katalog musi być publikowany;
przy przyszłym eksporcie/redystrybucji trzeba osobno ocenić warunki licencji OFF.

## Trwałość, backup i wdrożenie we własnej instancji

`init_db()` dodaje idempotentnie `food_products`, `food_product_versions`,
`food_draft_requests`, `food_portions`, `food_external_cache`, `food_external_rate`.
Nie usuwa dotychczasowych rekordów. Korekty i zatwierdzenia tworzą wersje.
Zdjęcie pozostaje w oryginalnym `agent_events.payload` w tej samej bazie;
produkt/rewizje zachowują `source_event_id`, także po korekcie ręcznej.
Nie powstaje osobny katalog plików zdjęć. SQLite backup API obejmuje katalog,
rewizje, porcje, cache i te oryginalne zdjęcia; baza może przez zdjęcia rosnąć.
Konfiguracja, sekrety i inne pliki spoza bazy nadal wymagają osobnego backupu
według istniejącej procedury. Nie kopiować samego aktywnego pliku DB bez WAL.

Przed wdrożeniem właściciel wykonuje dotychczasowy wspierany backup i sprawdza
odtworzenie na osobnej kopii. Po zatwierdzeniu review/CI samodzielnie aktualizuje
obraz według DEPLOY.md; start aplikacji inicjalizuje dodatkowe tabele.
Bez zmiany liczby workerów, uwierzytelniania, banków HS ani tokenów.
Moduły są wewnątrz istniejących katalogów `tools/` i `web/`, kopiowanych Dockerfile.
Do CHECK faktycznego obrazu dodano izolowany smoke SQLite/katalog/porcja/backup.

Repozytoryjny prompt może być nadpisany plikiem z DATA_DIR. Instrukcje katalogu
są dodatkowo dołączane przez agent.py, więc nie trzeba zastępować całego
własnego promptu. Właściciel powinien sprawdzić, czy jego instrukcje nie
konfliktują z procedurą szkic→jawne zatwierdzenie; nie odczytywano produkcyjnego promptu.

Rollback kodu: zatrzymać nowe zapisy, wykonać wspierany backup bieżącej bazy,
wrócić do poprzedniego zaakceptowanego obrazu. Dodatkowe tabele mogą pozostać;
starsza aplikacja ich nie użyje, dotychczasowe posiłki pozostają zwykłymi wierszami.
Pełne cofnięcie danych wymaga przywrócenia osobno sprawdzonego backupu sprzed
zmiany, ze świadomą utratą późniejszych zapisów. Nigdy nie usuwać tabel w działającej bazie.

## Faktyczna weryfikacja i bramki

2026-10-26: ograniczone publiczne GET przed adapterem dla5900531004544
(Skyr Naturalny/Piatnica, Polska,100g,64/12/4,1/0) i5901062003082
(podejrzany rekord mleka, niejednoznaczne100ml). Po implementacji rzeczywisty
adapter potwierdził pierwszy jako **unverified**. Drugi jest objęty konserwatywnym
odrzucaniem podstawy ml. To dowód istnienia tych rekordów, bez gwarancji
pokrycia polskiego rynku i dokładności. Surowe publiczne odpowiedzi zachowano
prywatnie w katalogu zadania, bez danych właściciela.

Testy używają fikcyjnych produktów i izolowanej bazy, HOME/DATA_DIR/auth/TMPDIR,
z blokadą sieci poza loopback. Syntetyczny provider testuje HTTP→kolejka→agent→
szkic→komenda właściciela→ponowne użycie→posiłek; nie jest to test live vision
ani OAuth. Chromium sprawdza logowanie, formularz, zatwierdzenie, porcję96kcal,
ponowne wczytanie i nieaktywne XSS. Wyniki końcowe: review-evidence/product-catalog.md.

Końcowy niezależny review źródła `2df48534b97f8d74d6aefb6ed8684b4ccad51292`
zakończył się PASS po naprawie walidacji energii OFF. Koordynator powtórzył pełne
testy i niezmienione probe'y. Bramka PR nadal wymaga rzeczywistego build/network-none
smoke na Actions forka dla dokładnego końcowego HEAD; link i stan są w opisie PR,
nie należy utożsamiać wcześniejszego przebiegu z CI nowego PR.
Wdrożenie pozostaje osobnym działaniem właściciela.
Przy jego odbiorze live: przesłać własną etykietę, porównać każde pole,
poprawić jedno pole, sprawdzić odrzucenie starej wersji, zatwierdzić aktualną,
zapisać znaną porcję i sprawdzić późniejszą rozmowę tekstową. Bez testowego
wysyłania prywatnych zdjęć lub prawdziwych danych podczas weryfikacji autora.

Dodatkowy ograniczony odczyt rzeczywistym adapterem potwierdził trzy kompletne
rekordy oznaczone rynkiem polskim:5900531004544 Skyr Naturalny,
5900531000102 Low Fat Cottage Cheese i5900531000010 SEREK WIEJSKI (Piątnica).
Wszystkie pozostały `unverified`,100g; to nie jest gwarancja poprawności etykiet
ani reprezentatywnego pokrycia rynku. Publiczny endpoint wyszukiwania zwrócił503;
sprawdzono pojedyncze produkty GET, bez zmiany adaptera i bez danych właściciela.

## Jeden logiczny posiłek w rozmowie

Chat zapisuje śniadanie jednym `log_meal`: `description`, pełna lista `ingredients`
(`product_id`, aktualna potwierdzona `version`, dodatnia `quantity`, `unit` g/ml),
i `remainder`. Reszta to albo `null` (brak składników spoza katalogu), albo opis
WYŁĄCZNIE części spoza katalogu z kompletem `calories`, `protein_g`, `carbs_g`,
`fat_g`. Dla posiłku całkowicie szacowanego lista jest pusta. Brak oszacowania
wymaga doprecyzowania. Makra katalogu wylicza serwer; nie doliczać ich do reszty.
Jawnie powtórzony składnik listy liczy się dwukrotnie. Limit: 100 pozycji;
ilość i każde oszacowanie 0–10000 (ilość >0), opis do 2000 znaków.

Jedna transakcja SQLite waliduje wszystkie pozycje, zapisuje jeden `posilki`,
niezmienny lokalny snapshot `meal_ingredients` i wynik w `meal_operations`.
`log_food_portion` usunięto ze schematu modelu; stara nazwa dispatchera odmawia
bez zapisu. Panelowy zapis pojedynczej porcji nadal działa dotychczasową ścieżką.
Nie dodano edytora składników, szablonów ani automatycznej naprawy historii.

Backend wiąże operację z właścicielem i tożsamością żądania z istniejącego turna
oraz slotem: jeden nowy posiłek na żądanie; update/delete osobno dla każdego ID.
Model nie wybiera klucza idempotencji. Dokładny replay zwraca historyczny wynik,
inna treść zajętego slotu daje konflikt. Nowa wiadomość stanowi nowe spożycie,
nawet gdy tekst jest podobny. Przy kilku niejednoznacznych posiłkach model ma
dopytać. Nie ma transakcji obejmującej inference lub całą rozmowę.

Update/delete i ledger commitują razem; brak ID jest błędem. Replay po późniejszej
korekcie/usunięciu nie zmienia danych i jest oznaczony jako historyczny. Korekta
zwiększa `posilki.revision`; oryginalny snapshot pozostaje niezmieniony. Kolejka
po awarii odpowiedzi lub restarcie odczytuje znane zatwierdzone operacje z ledgeru
(ID/liczba, bez opisów posiłków). Ponowienie dostawy nie uruchamia writera.
Inne rodzaje narzędzi nie są objęte tym rejestrem. Przed commit błąd wycofuje całą
operację; po commit błąd eventu, odpowiedzi lub dostawy nie wycofuje danych.

Migracja jest addytywna i idempotentna. Przed wdrożeniem właściciel wykonuje
spójny backup przez API SQLite wraz z dokumentami/zdjęciami i konfiguracją osobno,
a następnie próbę restore na kopii. Rollback: zatrzymać mutacje, zachować bieżący
backup, wrócić do poprzedniego obrazu bez DROP nowych tabel. Starszy writer traci
gwarancję grupowania/dedup; nie uruchamiać dwóch wersji writerów. Rzeczywisty obraz,
wdrożenie i live provider/OAuth pozostają osobnymi bramkami. Syntetyczne testy
trzech adapterów nie ustalają przyczyny dawnego błędu produkcyjnego: UNKNOWN.
