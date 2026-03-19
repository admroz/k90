# Libre PoC

PoC dla danych z FreeStyle Libre 2 prowadzony wewnątrz repo, ale poza kodem produkcyjnym `k90`.

Cel:
- sprawdzić, czy z Twojego obecnego setupu da się pobrać użyteczne dane,
- porównać dwa tory: oficjalny `LibreView` i nieoficjalny klient API,
- zebrać próbkę danych bez zapisu do głównej bazy SQLite.

Zakres tego katalogu:
- `poc_linkup.py` testuje nieoficjalny dostęp przez klienta Python,
- `notes.md` służy do zapisu ustaleń,
- `sample-output/` przechowuje lokalne, zanonimizowane lub tymczasowe próbki.

PoC nie:
- modyfikuje `agent.py`,
- nie zmienia `tools/`,
- nie zapisuje nic do `data/k90.db`.

## Tor 1: LibreView

Najpierw sprawdź oficjalną ścieżkę.

1. Wejdź na `https://www.libreview.com/`.
2. Spróbuj zalogować się tym samym kontem, którego używasz w aplikacji Libre na telefonie.
3. Sprawdź, czy widzisz historię glukozy i czy jest opcja pobrania danych z widoku `Glucose History`.
4. Zanotuj wynik w `notes.md`.

Minimalnie chcemy ustalić:
- czy logowanie działa,
- czy dane są widoczne,
- czy da się pobrać surowe dane lub raport eksportu,
- jaki zakres historii jest dostępny.

## Tor 2: Nieoficjalny klient API

Skrypt zakłada użycie biblioteki `libre-linkup-py`.

Instalacja lokalnie w venv:

```bash
pip install -r libre/requirements.txt
```

Skonfiguruj `libre/.env` na bazie `libre/.env.example`.

Minimalne zmienne:

```env
LIBRE_LINK_UP_USERNAME=twoj_login
LIBRE_LINK_UP_PASSWORD=twoje_haslo
LIBRE_LINK_UP_URL=https://api-eu2.libreview.io
LIBRE_LINK_UP_VERSION=4.16.0
```

Uruchomienie:

```bash
python libre/poc_linkup.py
```

Przydatne warianty:

```bash
python libre/poc_linkup.py --save-sample
python libre/poc_linkup.py --output libre/sample-output/manual-run.json
python libre/poc_linkup.py --redact
python libre/poc_linkup.py --print-client-methods
```

Skrypt:
- ładuje env tylko z `libre/.env`,
- loguje się,
- próbuje pobrać najnowszy odczyt,
- próbuje wykryć, czy klient potrafi zwrócić historię,
- wypisuje krótki raport diagnostyczny,
- opcjonalnie zapisuje próbkę JSON do `sample-output/`.

## Interpretacja wyniku

PoC uznajemy za udany, jeśli mamy:
- potwierdzone działanie logowania,
- co najmniej jeden realny rekord,
- jasność, czy dostępna jest historia, czy tylko ostatni odczyt,
- rekomendację jednej z dróg:
  `automat`, `eksport`, `odpuszczamy`.

Jeśli klient nieoficjalny działa niestabilnie, ale LibreView daje eksport, preferowany następny krok to importer eksportu zamiast stałego API.
