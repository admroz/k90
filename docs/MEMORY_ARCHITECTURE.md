# Pamięć k90 — kierunek rozwoju

**Status: uzgodnione wymagania i kierunek; bieżący odbiór w [STATUS.md](STATUS.md).**
Opis problemu i proponowanych warstw poniżej zachowuje punkt wyjścia projektu,
nie jest aktualnym raportem braku kodu. Implementację opisuje AGENTS.md,
a wykonane testy i niewykonane bramki — VERIFICATION.md.
Ten dokument zapisuje założenia pamięci długoterminowej. Nie uruchamia Hindsight,
nie migruje danych ani nie zmienia konfiguracji produkcyjnej. Zadania realizacyjne
pozostają w [TODO.md](../TODO.md), a bieżąca architektura w [AGENTS.md](../AGENTS.md).

## Problem w obecnej implementacji

- `conversations` przechowuje historię, ale `agent.load_history()` przekazuje do
  modelu tylko ostatnie `HISTORY_MESSAGES * 2` rekordów (domyślnie 10 par).
- `summary.py` buduje siedmioliniowy rekord z pięciu dokumentów pacjenta, nie
  z historii rozmów. Limit Chat Completions to domyślnie 600 tokenów;
  ścieżka Responses ma odrębny limit opisany w README.
- `tools/context.py` dokłada bieżący wyciąg pomiarów i posiłków, ale nie wyszukuje
  wcześniejszych ustaleń w rozmowach. Świeżo zbudowany kontekst nie gwarantuje
  świeżości danych źródłowych.

Informacja wypowiedziana w rozmowie może więc pozostać w SQLite, lecz wypaść
z kontekstu modelu, jeśli nie została świadomie zapisana w dokumentach.
Zwiększenie okna historii nie rozwiązuje długoterminowego wyszukiwania.

## Uzgodnione zasady

1. **Dane źródłowe należą do k90.** Pełna historia, dokumenty i potrzebne
   załączniki mają być przechowywane trwale, lokalnie i objęte backupem,
   niezależnie od dostawcy pamięci. Docelowo obejmuje to także wersje i korekty;
   dzisiejszy zapis rozmów nie jest kompletnym dziennikiem wszystkich operacji.
2. **Hindsight jest wymienialnym indeksem pamięci**, nie jedynym magazynem
   ani źródłem prawdy dla pomiarów, posiłków i aktualnego stanu pacjenta.
3. **Kontekst ma wracać do źródeł.** Wynik pamięci powinien wskazywać datę
   i lokalne identyfikatory wiadomości, umożliwiając odczyt sąsiedniego fragmentu
   rozmowy. Sam wyekstrahowany fakt nie zastępuje oryginału.
4. **Awaria pamięci nie blokuje rozmowy ani zapisu.** Wyłączenie Hindsight
   pozostawia lokalne dane i podstawową funkcjonalność aplikacji.
5. **Oddzielamy pamięć k90 od innych agentów.** Wspólna instancja usługi jest
   dopuszczalna, ale nie wspólny bank ani automatyczny dostęp do pamięci zdrowotnej.
6. Przetwarzanie zewnętrzne jest dopuszczonym założeniem wdrożenia; lokalne
   modele nie są wymagane. Nie oznacza to zgody na wysyłanie dowolnych danych.

## Proponowane warstwy

| Warstwa | Odpowiedzialność |
| --- | --- |
| SQLite i lokalne pliki | Źródłowa historia, pomiary, posiłki, dokumenty, załączniki i wersje; eksport oraz backup niezależny od HS. |
| Krótki profil w kontekście | Aktualne, potwierdzone informacje istotne dla odpowiedzi; bez polegania wyłącznie na trafności wyszukiwania. |
| Adapter pamięci | Wymienny interfejs zapisu i wyszukiwania; pierwszy backend: Hindsight. |
| Lokalny indeks tekstowy | Proponowany fallback SQLite FTS5 do wyszukiwania starszych rozmów bez HS i bez modelu lokalnego. |

Nie indeksujemy domyślnie każdego pomiaru Garmin/Libre w HS. Dokładne wartości
czytamy z SQLite; pamięć ma przede wszystkim odnajdywać ustalenia, preferencje,
powody decyzji oraz kontekst wydarzeń i wcześniejszych prób.

## Proponowany przepływ

```text
Wiadomość → lokalny zapis + zlecenie indeksowania (jedna transakcja)
                                   ↓
                       lokalna polityka prywatności
                                   ↓
                         trwała kolejka / retry
                                   ↓
                       adapter → Hindsight, bank k90

Pytanie → polityka prywatności → wyszukiwanie HS / lokalny fallback
       → identyfikatory źródeł → lokalny fragment rozmowy z datą
       → ponowna kontrola prywatności → kontekst odpowiedzi modelu
```

- Automatyczny recall przed odpowiedzią, z limitem czasu i budżetem kontekstu;
  nie polegamy wyłącznie na decyzji modelu o użyciu narzędzia pamięci.
- Zapis indeksu asynchroniczny, z trwałym stanem zleceń i retry. Awaria między
  lokalnym zapisem a wywołaniem HS nie może zgubić materiału do indeksowania.
- Stabilne identyfikatory źródeł, wersje i operacje aktualizacji/usunięcia muszą
  umożliwiać bezpieczne ponowienia bez niekontrolowanych duplikatów. Szczegóły
  semantyki API należy sprawdzić dla wdrożonej wersji Hindsight.
- Korekta musi unieważniać zastąpione dane w indeksie. Zdarzenie historyczne
  nie jest automatycznie aktualnym stanem; plan nie jest wykonanym działaniem,
  a sugestia asystenta nie jest deklaracją użytkownika.
- Odtwarzanie indeksu odbywa się z lokalnych źródeł, według aktualnej polityki
  prywatności. Nie wymaga odzyskiwania danych z HS.

## Prywatność i granice wysyłania

**Poniższe zabezpieczenia są wymaganiami projektu, nie opisem obecnego kodu.**

- Lokalnie maskować bezpośrednie identyfikatory (np. nazwisko, PESEL, adres,
  telefon, e-mail, identyfikatory kont/pacjenta) i blokować sekrety.
- Osobno ustalić dozwolone kategorie kontekstu zdrowotnego oraz treści oznaczone
  jako wyłącznie lokalne. Maskowanie identyfikatorów nie czyni danych anonimowymi.
- Kontrolować wszystkie wyjścia do modeli: rozmowę, summary, wyniki narzędzi,
  indeksowanie i zapytania pamięci, w tym ewentualne embeddings/reflect.
  Przywrócenie oryginalnego cytatu lokalnie nie może omijać kontroli wysyłki.
- Nie wysyłać surowych danych do chmurowego modelu tylko po to, aby je ocenzurował.
  Lokalne reguły i walidatory nie wymagają dużego modelu, ale nie gwarantują
  wykrycia każdego identyfikatora w dowolnym tekście.
- Przy wykrytej niepewności lub błędzie filtra nie wysyłać oryginału; zachować
  lokalny zapis i jawnie ograniczyć operację. Rozmowa wymagająca zablokowanych
  danych może pozostać bez odpowiedzi modelu — brak wysyłki jest ważniejszy.
- Załączniki i obrazy wymagają odrębnej polityki; filtr tekstowy ich nie chroni.
  Nie importować ich automatycznie do HS przed ustaleniem tej polityki.
- Logi, błędy i metadane również nie mogą ujawniać sekretów lub blokowanych treści.
  Lokalne oryginały i backupy wymagają własnej kontroli dostępu i retencji.

## Wspólna usługa Hindsight

Docelowo jedna instancja może obsługiwać oddzielne banki innych agentów i k90.
Bank `k90-owner` jest proponowaną nazwą, nie istniejącym ustawieniem aplikacji.
Osobny bank stanowi granicę wyszukiwania, ale sam nie dowodzi kontroli uprawnień.
Przed podłączeniem ustalić uwierzytelnianie, ograniczenia dostępu, sieć prywatną,
backupy, limity zasobów i zachowanie przy awarii wspólnej usługi.

Nie dodajemy w tym PR konfiguracji Compose, endpointów ani kluczy.
Punktem wyjścia uzgodnień jest istniejąca usługa HS korzystająca z Codex oraz
k90 korzystające z OpenAI API; faktyczną konfigurację należy zweryfikować przed
integracją. Model i sposób uwierzytelnienia HS pozostają szczegółem
adaptera/wdrożenia, niezależnym od modelu rozmowy k90. Lokalny kontener HS nie
oznacza lokalnego przetwarzania przez modele.

## Etapy i kryteria odbioru

Najpierw pilot na fikcyjnych danych i osobnym banku testowym, potem kontrolowany
import wybranych źródeł. Bez automatycznego importu całej produkcyjnej historii.

Pierwsza wersja powinna wykazać, że:

- ustalenie wraca po wypadnięciu z okna rozmowy, z datą i poprawnym źródłem;
- korekta zastępuje stary stan, a plan i sugestia modelu nie stają się faktem;
- restart i ponowienie nie gubią źródeł ani nie dublują indeksowanych zdarzeń;
- niedostępny HS nie blokuje lokalnego zapisu i uruchamia ograniczony fallback;
- indeks da się odbudować od zera po usunięciu banku testowego;
- zabronione treści nie opuszczają aplikacji również w recall, wynikach narzędzi,
  summary, załącznikach i błędach; sprawdzamy to atrapami odbiorców;
- wyłączenie adaptera pozostawia czytelną historię i działające podstawowe funkcje.

**Do ustalenia przed implementacją:** dokładny schemat danych i załączników,
rozmiar fragmentów i budżet recall, polityka identyfikatorów i danych zdrowotnych,
uprawnienia do banku, retencja/usuwanie oraz miary jakości, kosztów i opóźnień.
