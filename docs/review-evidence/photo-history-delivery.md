# Odbiór poprawki historii zdjęć i SIWC host-ID

Testowane i niezależnie ocenione źródło: `b8091b7a03ac2de7010d7a1408eb44a3f09d24d9`.
Baza zakresu PR: `17beba2353cbc1e1a2d39d71bc9b5a78f11a2ed4`. Późniejsze commity
w tej gałęzi zmieniają wyłącznie dokumentację i dowody, nie kod ani testy.

## Wynik przygotowania kodu

- `photo-history-independent.json`: świeży niezależny review PASS, bez otwartych
  ustaleń, obejmujący również poprawkę host-ID. Oryginalny raport recenzenta
  zachowany jako `photo-history-review-resumed.json` i `.md`.
- `photo-history-acceptance.json`: odbiór syntetyczny PASS pięciu wymaganych
  zakresów. Niezależny recenzent wykonał 482 testy repo / 1 skip, osobno 79 probes,
  21 testów frontend i kontrolę składni JS. Koordynator następnie wykonał razem
  561 testów Python / 1 skip oraz ponownie 21 frontend i kontrolę składni JS.
  Jedyny skip dotyczy niewybranego lokalnego importu; nie pominięto nowego guardu.
- R1 zamknięte: nieznane/błędne części historii muszą zgłosić PrivacyError przed
  providerem. Adaptowany probe sprawdza wyjątek, brak transportu i niezmieniony
  zapis SQL. Oryginalny FAIL i stare probes zachowano bez przepisywania wyniku.
- Każdy modelowy wariant API/Responses/subskrypcja i lokalny backend/rzeczywisty
  adapter HS z syntetycznym transportem jest objęty macierzą rozmowy.
- Kontrola sekretów/local-only obejmuje oryginał PRZED odrzuceniem obrazów,
  w tym metadane i zagnieżdżony kodowany JSON. Filtr prywatności nie jest pełną
  anonimizacją. Nie zdejmowano ograniczeń obrazów dla HS.

Wszystkie sąsiednie pliki `photo-history-review-resumed-*` są kopiami dowodów
recenzenta. Jego oryginalne absolutne ścieżki TASK w JSON/raporcie celowo
pozostają niezmienione. Do ponownego wykonania 79 probes można użyć skopiowanego
`docs/review-evidence/photo-history-review-resumed-probes.py`; wymagane env -i,
izolowany syntetyczny DB/DATA/HOME/auth i nowy scratch basetemp opisano w manifeście.
Nie czytać produkcyjnego `.env` ani danych dla odtworzenia testów.

## Kontrakt zdjęć

Nowe celowo wysłane zdjęcie posiłku wymaga jawnego ustawienia
`K90_ALLOW_MODEL_IMAGES=true` w prywatnej konfiguracji k90. Domyślnie zgoda jest
wyłączona. Flaga pozwala przekazać nowe zdjęcie zewnętrznemu modelowi vision;
nie rozszerza zgody na PII, archiwa ani HS. Sama flaga nie naprawia starej historii.

Kolejne tury przekazują bezpieczny tekst, wcześniejszą analizę asystenta i korekty
użytkownika. Rozpoznane stare obrazy zastępuje `[Historical image omitted]`, nawet
przy włączonej fladze. Nie ma automatycznego opisu starych archiwów, migracji ani
zmiany lokalnych oryginałów. Brak starego opisu pozostaje uczciwie brakiem opisu.
Nie dodano wywołań LLM ani automatycznego zapisu posiłku z niepewnego rozpoznania.
Ostatni zapisany posiłek nadal ustala się przez kanoniczne narzędzia SQLite.

## CI, PR i wdrożenie to osobne etapy

Dokładny HEAD, zdalny SHA, numer/URL i świeży odczyt stanu PR oraz CI koordynator
zapisuje w prywatnym TASK `pr-verification.json` i `outcome.json`. Manifest PASS
kodowy nie jest dowodem zielonego CI ani wdrożenia. Nie mylić wcześniejszych
runów/źródłowego SHA z CI końcowego dokumentacyjnego HEAD.

Przeczytano cały `.github/workflows/docker.yml`: dispatch tej gałęzi oraz PR
wykonują testy, rzeczywisty Docker build i izolowane smoke bez zewnętrznej sieci;
publikacja jest pomijana poza main. Merge do upstream main uruchomi testy i
publikację AMD64 `admroz/k90:latest` oraz tagu SHA. ARM pozostaje wyłączony.
Push/PR nie wdraża kontenera. Nie włączano auto-merge ani prawa maintainer edits.

## Instrukcja właściciela po przeglądzie i merge

1. Wykonać dotychczasowy wspierany backup k90: spójny backup SQLite (nie samo
   kopiowanie aktywnego pliku z pominięciem WAL), dokumenty/załączniki i prywatną
   konfigurację oraz osobny magazyn SIWC k90. Zanotować aktualny tag/digest obrazu.
   Backupów, sekretów ani oryginalnych zdjęć nie dodawać do Git.
2. Po zielonej publikacji wybrać konkretny tag/digest obrazu wynikający z merge,
   nie zakładać, że będzie równy SHA gałęzi PR. Dodać jawne
   `K90_ALLOW_MODEL_IMAGES=true` tylko do prywatnej konfiguracji k90, jeśli mają
   być przetwarzane nowe zdjęcia. Nie zmieniać stacku ani magazynu Hermesa/HS.
3. Wdrożyć samodzielnie istniejącą procedurą. Sprawdzić health, zwykły tekst po
   starej historii ze zdjęciem, nowy posiłek ze zdjęciem i tekstowe doprecyzowanie
   porcji/przygotowania. Testy z atrapą providera nie dowodzą trafności realnego
   rozpoznania; to osobny smoke właściciela. Przed zapisem posiłku zatwierdzić dane.
4. Zweryfikować brak ponownego wysyłania starych obrazów i brak obrazów w HS,
   bez ujawniania zawartości rozmów/tokenów w logach. Live topologia/autoryzacja
   HS i rzeczywisty retain/recall pozostają odroczone do właściciela.
5. Rollback: powrót do zanotowanego poprzedniego tagu/digestu (według zgłoszenia
   właściciela przed PR `admroz/k90:sha-17beba2`) z zachowaniem danych i magazynu
   SIWC; w razie konieczności odtworzenie spójnego backupu świadomie przez
   właściciela. Stary obraz może ponownie ujawnić błąd historii. Wyłączenie zgody
   blokuje nowe zdjęcia, ale nie zastępuje cofnięcia obrazu.

Nie wykonano produkcyjnego logowania, odczytów prywatnych, migracji realnej
historii, zmian HS, merge ani wdrożenia. Pełny syntetyczny PASS nie jest
certyfikacją produkcji ani jej autoryzacji.
