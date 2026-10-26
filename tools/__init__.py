"""Rejestr narzędzi agenta — definicje JSON i dispatcher."""

import json
from .health import (
    get_blood_pressure, get_weight_trend, get_sleep_stats,
    get_activities, get_hrv, get_body_battery, get_daily_metrics, get_glucose_readings,
)
from .lab import get_lab_results
from .diet import log_meal, update_meal, get_recent_meals, delete_meal
from .garmin import sync_garmin_data
from .libre import sync_libre_data
from .patient import read_patient_file, update_patient_file
from .food_catalog import propose_from_chat, search as find_food_products, log_portion_from_chat
from .food_off import lookup as lookup_food_barcode


def _refresh_patient_summary() -> dict:
    from summary import refresh_patient_summary
    summary = refresh_patient_summary(trigger="tool_call")
    return {"ok": True, "length": len(summary)}


# Mapa nazwa → funkcja
_REGISTRY = {
    "lookup_food_barcode": lookup_food_barcode,
    "propose_food_product": propose_from_chat,
    "find_food_products": find_food_products,
    "log_food_portion": log_portion_from_chat,
    "get_blood_pressure": get_blood_pressure,
    "get_weight_trend": get_weight_trend,
    "get_sleep_stats": get_sleep_stats,
    "get_activities": get_activities,
    "get_hrv": get_hrv,
    "get_body_battery": get_body_battery,
    "get_daily_metrics": get_daily_metrics,
    "get_glucose_readings": get_glucose_readings,
    "get_lab_results": get_lab_results,
    "log_meal": log_meal,
    "update_meal": update_meal,
    "get_recent_meals": get_recent_meals,
    "delete_meal": delete_meal,
    "sync_garmin_data": sync_garmin_data,
    "sync_libre_data": sync_libre_data,
    "read_patient_file": read_patient_file,
    "update_patient_file": update_patient_file,
    "refresh_patient_summary": _refresh_patient_summary,
}

# Definicje narzędzi w formacie OpenAI (kompatybilny z LiteLLM)
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_blood_pressure",
            "description": "Pobiera pomiary ciśnienia krwi z ostatnich N dni.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "Liczba dni wstecz (domyślnie 30)", "default": 30}
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weight_trend",
            "description": "Pobiera historię wagi z ostatnich N dni.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "Liczba dni wstecz (domyślnie 90)", "default": 90}
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_sleep_stats",
            "description": "Pobiera dane dotyczące snu z ostatnich N dni.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "Liczba dni wstecz (domyślnie 14)", "default": 14}
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_activities",
            "description": "Pobiera aktywności fizyczne z ostatnich N dni.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "Liczba dni wstecz (domyślnie 14)", "default": 14},
                    "activity_type": {"type": "string", "description": "Opcjonalny filtr typu aktywności (np. cycling, hiking)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_hrv",
            "description": "Pobiera dane HRV (zmienność rytmu serca) z ostatnich N dni.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "Liczba dni wstecz (domyślnie 14)", "default": 14}
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_body_battery",
            "description": "Pobiera dane Body Battery z Garmina z ostatnich N dni.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "Liczba dni wstecz (domyślnie 7)", "default": 7}
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_daily_metrics",
            "description": "Pobiera dzienne metryki zdrowotne (RHR, stres, oddech) oraz kalorie spoczynkowe, aktywne i spalone łącznie z Garmin z ostatnich N dni. Do bilansu używaj tych kalorii, bez dodawania kalorii treningów. Brak danych nie oznacza zera ani stałego BMR.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "Liczba dni wstecz (domyślnie 14)", "default": 14}
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_glucose_readings",
            "description": "Pobiera odczyty glukozy z FreeStyle Libre z ostatnich N dni.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "Liczba dni wstecz (domyślnie 2)", "default": 2}
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_lab_results",
            "description": "Pobiera wyniki badań laboratoryjnych, opcjonalnie filtrując po kategorii lub nazwie.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "Kategoria badań (np. glukoza, lipidy, witaminy, nerki)"},
                    "test_name": {"type": "string", "description": "Nazwa konkretnego badania (np. HbA1c, LDL, eGFR)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "log_meal",
            "description": "Zapisuje informację o spożytym posiłku do bazy danych. Po udanym zapisie w odpowiedzi dla użytkownika podaj dokładnie id, datę i godzinę zwrócone przez narzędzie.",
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {"type": "string", "description": "Opis posiłku (np. owsianka z jagodami i orzechami)"},
                    "calories": {"type": "number", "description": "Szacowana liczba kalorii; wymagane"},
                    "protein_g": {"type": "number", "description": "Białko w gramach; wymagane"},
                    "carbs_g": {"type": "number", "description": "Węglowodany w gramach; wymagane"},
                    "fat_g": {"type": "number", "description": "Tłuszcze w gramach; wymagane"},
                    "notes": {"type": "string", "description": "Dodatkowe uwagi"},
                    "date": {"type": "string", "description": "Data posiłku w formacie YYYY-MM-DD (domyślnie dzisiaj)"},
                    "time": {"type": "string", "description": "Godzina posiłku w formacie HH:MM (domyślnie teraz)"},
                },
                "required": ["description", "calories", "protein_g", "carbs_g", "fat_g"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_meal",
            "description": "Aktualizuje istniejący posiłek w bazie danych. Używaj do korekty opisu, kalorii i makroskładników już zapisanego wpisu zamiast usuwać i dodawać go od nowa, jeśli użytkownik poprawia wcześniejszy zapis.",
            "parameters": {
                "type": "object",
                "properties": {
                    "meal_id": {"type": "integer", "description": "ID posiłku do aktualizacji (z get_recent_meals)"},
                    "description": {"type": "string", "description": "Poprawiony opis posiłku"},
                    "calories": {"type": "number", "description": "Poprawiona liczba kalorii; wymagane"},
                    "protein_g": {"type": "number", "description": "Poprawione białko w gramach; wymagane"},
                    "carbs_g": {"type": "number", "description": "Poprawione węglowodany w gramach; wymagane"},
                    "fat_g": {"type": "number", "description": "Poprawione tłuszcze w gramach; wymagane"},
                    "notes": {"type": "string", "description": "Dodatkowe uwagi"},
                    "date": {"type": "string", "description": "Data posiłku w formacie YYYY-MM-DD; opcjonalnie"},
                    "time": {"type": "string", "description": "Godzina posiłku w formacie HH:MM; opcjonalnie"},
                },
                "required": ["meal_id", "description", "calories", "protein_g", "carbs_g", "fat_g"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_meal",
            "description": "Usuwa posiłek z bazy danych na podstawie ID. Używaj gdy użytkownik prosi o usunięcie lub korektę błędnie zapisanego posiłku.",
            "parameters": {
                "type": "object",
                "properties": {
                    "meal_id": {"type": "integer", "description": "ID posiłku do usunięcia (z get_recent_meals)"},
                },
                "required": ["meal_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_meals",
            "description": "Pobiera ostatnio zalogowane posiłki z ostatnich N dni. Używaj także wtedy, gdy użytkownik odwołuje się do wcześniejszego posiłku albo konkretnego dnia, np. piątku.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "Liczba dni wstecz (domyślnie 3)", "default": 3}
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sync_garmin_data",
            "description": "Pobiera nowe dane z Garmin Connect i aktualizuje bazę danych. Używaj gdy użytkownik prosi o synchronizację lub odświeżenie danych z Garmina.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sync_libre_data",
            "description": "Pobiera najnowsze dane glukozy z LibreLinkUp i aktualizuje bazę danych. Używaj tylko gdy użytkownik wyraźnie prosi o odświeżenie danych glukozy teraz albo gdy odpowiedź wymaga najświeższego możliwego odczytu, np. dla korelacji dzisiejszych posiłków z obecną glukozą. Nie używaj rutynowo do zwykłej analizy, bo system robi auto-sync Libre raz dziennie.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_patient_file",
            "description": "Wczytuje plik danych pacjenta (pacjent.md, wywiad.md, analiza.md, dieta.md, tydzien.md).",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "Nazwa pliku: pacjent.md, wywiad.md, analiza.md, dieta.md lub tydzien.md"},
                },
                "required": ["filename"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_patient_file",
            "description": "Zapisuje zaktualizowaną treść pliku danych pacjenta. Używaj gdy Adam dostarcza nowe informacje (wyniki badań, zmiana wagi, nowe leki, nowe ulubione dania itp.).",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "Nazwa pliku: pacjent.md, wywiad.md, analiza.md, dieta.md lub tydzien.md"},
                    "content": {"type": "string", "description": "Pełna nowa treść pliku"},
                },
                "required": ["filename", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "refresh_patient_summary",
            "description": "Odświeża podsumowanie danych pacjenta na podstawie wszystkich plików medycznych. Używaj gdy zaszły istotne zmiany (nowe wyniki badań, zmiana leków, ważny nowy fakt medyczny).",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
]


for _name, _description, _properties, _required in [
    ('lookup_food_barcode', 'Lokalnie najpierw, OFF zapasowo. Zewnętrzny wynik zawsze niepotwierdzony; nie importuj jako etykiety.',
     {'barcode':{'type':'string'}}, ['barcode']),
    ('propose_food_product', 'Zapisz wyłącznie szkic etykiety do jawnej kontroli użytkownika.',
     {'product': {'type': 'object', 'properties': {
         **{k: {'type':'string'} for k in ('name','brand','barcode')},
         'basis': {'type':'string','enum':['100g','100ml']},
         'provenance': {'type':'string','enum':['own_label','manual']},
         **{k: {'type':'number'} for k in ('kcal','protein','carbs','fat')}},
         'required':['name','basis','provenance','kcal','protein','carbs','fat']}}, ['product']),
    ('find_food_products', 'Lokalny katalog; najpierw dokładny kod, potem ograniczone wyszukiwanie nazwy.',
     {'query':{'type':'string'}, 'barcode':{'type':'string'}}, []),
    ('log_food_portion', 'Zapisz jedną porcję potwierdzonego produktu; nie powtarzaj log_meal.',
     {'product_id':{'type':'integer'}, 'version':{'type':'integer'}, 'quantity':{'type':'number'},
      'unit':{'type':'string','enum':['g','ml']}, 'request_id':{'type':'string'}},
     ['product_id','version','quantity','unit','request_id']),
]:
    TOOLS.append({'type':'function','function':{'name':_name,'description':_description,
                 'parameters':{'type':'object','properties':_properties,'required':_required}}})


def execute_tool(name: str, args: dict):
    """Wykonuje narzędzie o podanej nazwie z podanymi argumentami."""
    fn = _REGISTRY.get(name)
    if fn is None:
        return {"error": f"Nieznane narzędzie: {name}"}
    try:
        from memory_runtime import TURN_CONTEXT
        turn = TURN_CONTEXT.get()
        is_meal = name in ('log_meal', 'log_food_portion')
        if turn and is_meal and turn.get('meal_log_kind') not in (None, name):
            return {'error':'Nie łącz log_meal i log_food_portion w jednej wiadomości. Porcja mogła już zostać zapisana; osobny posiłek zgłoś w nowej wiadomości.'}
        result = fn(**args)
        if turn and is_meal and isinstance(result, dict) and 'error' not in result:
            turn['meal_log_kind'] = name
        return result
    except Exception as e:
        return {"error": str(e)}
