# Libre PoC Notes

Data rozpoczęcia: 2026-03-19

## Checklist

- [x] Login do LibreView działa
- [ ] W LibreView widać historię glukozy
- [ ] Da się pobrać dane z LibreView
- [x] `poc_linkup.py` loguje się poprawnie
- [x] `poc_linkup.py` zwraca najnowszy odczyt
- [x] `poc_linkup.py` znajduje historię lub potwierdza jej brak
- [x] Jest lokalna próbka w `sample-output/`

## LibreView

- Status: login działa, ale PoC poszedł dalej przez LibreLinkUp API.
- Konto / region: PL
- Czy widać historię: niezweryfikowane do końca w samym LibreView
- Czy jest eksport:
- Zakres historii:
- Uwagi: eksport z LibreView nadal warto sprawdzić osobno, jeśli będzie potrzebna gęstsza historia niż `graphData`.

## API / klient nieoficjalny

- Status: działa
- Użyta biblioteka: `libre-linkup-py`
- Czy login działa: tak
- Czy latest działa: tak, przez `glucoseMeasurement`
- Czy historia działa: tak, przez `graphData`
- Jakie pola są dostępne: `Timestamp`, `FactoryTimestamp`, `ValueInMgPerDl`, `Value`, `TrendArrow`, `TrendMessage`, `MeasurementColor`, `isHigh`, `isLow`, `type`
- Uwagi:
  - konto wymagało połączenia LibreLinkUp z LibreView,
  - domyślny klient miał błąd dla kraju `PL`, więc `poc_linkup.py` omija wadliwy parser czasu i czyta surowe payloady,
  - `graphData` daje historię co ok. 15 minut,
  - `glucoseMeasurement` jest nowszy niż ostatni punkt `graphData`, więc nadaje się jako bieżący odczyt.

## Wniosek

- Rekomendacja: iść dalej z integracją opartą o LibreLinkUp.
- Następny krok: dodać właściwy sync do SQLite z `graphData` jako bazą historii i `glucoseMeasurement` jako opcjonalnym bieżącym punktem.
- Ryzyka:
  - historia z API ma dziś granularność ok. 15 minut,
  - 1-min polling można dodać później, ale nie odtworzy luk z downtime,
  - katalog `libre/` jest tymczasowy; po wdrożeniu finalnego syncu jego zawartość można usunąć albo zostawić tylko jako notatkę historyczną.
