"""Rejestr narzędzi agenta — definicje JSON i dispatcher."""

import json
from .health import (
    get_blood_pressure, get_weight_trend, get_sleep_stats,
    get_activities, get_hrv, get_body_battery, get_daily_metrics, get_glucose_readings,
)
from .lab import get_lab_results
from .diet import log_meal, get_recent_meals, delete_meal
from .garmin import sync_garmin_data
from .libre import sync_libre_data
from .patient import read_patient_file, update_patient_file


def _refresh_patient_summary() -> dict:
    from summary import refresh_patient_summary
    summary = refresh_patient_summary(trigger="tool_call")
    return {"ok": True, "length": len(summary)}


# Mapa nazwa → funkcja
_REGISTRY = {
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
            "description": "Pobiera dzienne metryki zdrowotne (RHR, stres, oddech) z ostatnich N dni.",
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
                    "calories": {"type": "number", "description": "Szacowana liczba kalorii"},
                    "protein_g": {"type": "number", "description": "Białko w gramach"},
                    "carbs_g": {"type": "number", "description": "Węglowodany w gramach"},
                    "fat_g": {"type": "number", "description": "Tłuszcze w gramach"},
                    "notes": {"type": "string", "description": "Dodatkowe uwagi"},
                    "date": {"type": "string", "description": "Data posiłku w formacie YYYY-MM-DD (domyślnie dzisiaj)"},
                    "time": {"type": "string", "description": "Godzina posiłku w formacie HH:MM (domyślnie teraz)"},
                },
                "required": ["description"],
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


def execute_tool(name: str, args: dict):
    """Wykonuje narzędzie o podanej nazwie z podanymi argumentami."""
    fn = _REGISTRY.get(name)
    if fn is None:
        return {"error": f"Nieznane narzędzie: {name}"}
    try:
        return fn(**args)
    except Exception as e:
        return {"error": str(e)}
