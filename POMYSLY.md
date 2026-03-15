# Pomysły na rozwój k90

## Zebrane 2026-03-15

### Jakość rozpoznawania
- Użyć Sonnet zamiast Haiku do analizy zdjęć jedzenia — Haiku mylił ryż brązowy z makaronem

### Obsługa dokumentów
- PDF przez Signal — przesyłanie wyników badań do analizy
- Aktualnie obsługujemy tylko zdjęcia; trzeba sprawdzić czy signal-cli-rest-api zwraca załączniki PDF i jak je przekazać do modelu

### Observability
- Więcej logów i metryk — żeby w razie problemów wiedzieć co się działo
- Może osobny plik logu z wywołaniami narzędzi, tokenami, błędami?

### Raportowanie
- Agent generujący wykresy (matplotlib?) lub zestawienia w PDF
- Tygodniowe/miesięczne raporty zdrowotne

### Interfejs webowy
- Wystawić dane jako aplikację webową — ożywić stare statyczne strony HTML (dashboard, dieta)
- Połączyć z bazą SQLite na żywo
- Ewentualnie integracja z aplikacją do diety

---

## Moje propozycje

- **Auto-sync Garmin** — cron w kontenerze który raz dziennie ciągnie dane, zamiast ręcznego "pobierz dane z Garmina"
- **Powiadomienia proaktywne** — agent sam wysyła rano skrót: waga, HRV, plan dnia żywieniowy
- **Kontekst sezonowy / cykliczny** — agent świadomy np. czy to dzień po treningu, żeby lepiej oceniać kalorie i odpoczynek
- **Backup bazy** — automatyczny rsync bazy na laptopa np. raz dziennie (odwrotność pull)
- **Selektywny trigger CI/CD** — pliki typu `POMYSLY.md`, `README.md`, `DEPLOY.md` nie powinny wyzwalać przebudowy obrazu w GitHub Actions; dodać path filters w workflow (`paths:` z excludes dla plików docs)
