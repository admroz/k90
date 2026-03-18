# Pomysły na rozwój k90

## PRIORYTETY

- przejście na Codex w pracy i OpenAI API w agencie
- nieprawidłowa strefa czasowa (jednorazowy fix bazy?)
- dodać komendę /update żeby pobieranie nowych danych nie przechodziło przez LLM
-

## Zebrane 2026-03-15

### Jakość rozpoznawania
- Użyć Sonnet zamiast Haiku do analizy zdjęć jedzenia — Haiku mylił ryż brązowy z makaronem

### Różne
- chyba mamy nieprawidłową strefę czasową
- przenieść wszystko do bazy zamiast trzymać w plikach .md? (musi zadziałać migracja schematu bez straty obecych danych)
- ładować dane garmin prosto do bazy, bez pośrednictwa plików .csv?
- ładować tylko to czego rzeczywiście brakuje, teraz dziwnie pokazuje status (jakby zawsze ładował tydzień do tyłu, a nie tylko to co nowe)
- komentarze w kodzie powinny być po angielsku, wywalić pozostałe wystąpienia "kadencja90"

### Obsługa dokumentów
- PDF przez Signal — przesyłanie wyników badań do analizy
- wyniki mogą też być wysłane jako zdjęcie - powinno być rozpoznawanie czy na zdjęciu jest posiłek czy dokument, a może jeszcze co innego?
- Aktualnie obsługujemy tylko zdjęcia; trzeba sprawdzić czy signal-cli-rest-api zwraca załączniki PDF i jak je przekazać do modelu

### Observability
- Więcej logów i metryk — żeby w razie problemów wiedzieć co się działo
- Logi z głównej pętli agenta, chciałbym zobaczyć jak dokładnie odpowiada agent z prośbami o wywołanie tooli (skąd wie, jakie toole są dostępne? muszą być wymienione w system_prompt, o innych nie wie?)
- Może osobny plik logu z wywołaniami narzędzi, tokenami, błędami?
- /summary - pokazuje co ma wpisane w summary
- czy mam shell wewnątrz kontenera żeby zajrzeć w logi?

### Raportowanie
- Agent generujący wykresy (matplotlib?) lub zestawienia w PDF
- Tygodniowe/miesięczne raporty zdrowotne

### Interfejs webowy
- Wystawić dane jako aplikację webową — ożywić stare statyczne strony HTML (dashboard, dieta)
- Połączyć z bazą SQLite na żywo
- Ewentualnie integracja z aplikacją do diety

### Backup lokalny
- w fazie testów może odkładać raz na dobę (o północy?) tar.gz całego folderu data
- rotować max 30 dni
- konieczność podmontowania kolejnego folderu?

### Język (do rozważenia!)
- podobno po angielsku zużywa się mniej tokenów
- może komunikacja z userem po polsku, ale system prompty po angielsku
- może to jednak za dużo zamieszania?

### Nowy typ danych
- FreeStyle Libre 2

---

## Moje propozycje

- **Auto-sync Garmin** — cron w kontenerze który raz dziennie ciągnie dane, zamiast ręcznego "pobierz dane z Garmina"
- **Powiadomienia proaktywne** — agent sam wysyła rano skrót: waga, HRV, plan dnia żywieniowy
- **Kontekst sezonowy / cykliczny** — agent świadomy np. czy to dzień po treningu, żeby lepiej oceniać kalorie i odpoczynek
- **Backup bazy** — automatyczny rsync bazy na laptopa np. raz dziennie (odwrotność pull)
- **Selektywny trigger CI/CD** — pliki typu `POMYSLY.md`, `README.md`, `DEPLOY.md` nie powinny wyzwalać przebudowy obrazu w GitHub Actions; dodać path filters w workflow (`paths:` z excludes dla plików docs)
