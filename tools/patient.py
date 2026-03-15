"""Narzędzia do odczytu i aktualizacji plików danych pacjenta."""

import os
from pathlib import Path

DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data"))

ALLOWED_FILES = {
    "pacjent.md", "wywiad.md", "analiza.md",
    "dieta.md", "tydzien.md",
}
FORBIDDEN = {"system_prompt.md"}


def read_patient_file(filename: str) -> dict:
    """Wczytuje plik danych pacjenta (pacjent.md, wywiad.md, analiza.md, dieta.md, tydzien.md).

    Args:
        filename: Nazwa pliku do odczytania.

    Returns:
        Słownik z kluczem 'content' (treść pliku) lub 'error'.
    """
    if filename in FORBIDDEN:
        return {"error": f"Plik {filename} jest chroniony i nie może być odczytany."}
    path = DATA_DIR / filename
    if not path.exists():
        return {"error": f"Plik {filename} nie istnieje."}
    return {"filename": filename, "content": path.read_text(encoding="utf-8")}


def update_patient_file(filename: str, content: str) -> dict:
    """Zapisuje zaktualizowaną treść pliku danych pacjenta.

    Używaj gdy: aktualizujesz profil po nowych badaniach, dodajesz posiłek do tydzien.md,
    zapisujesz nowe obserwacje w analiza.md itp.
    Nigdy nie używaj do system_prompt.md.

    Args:
        filename: Nazwa pliku do zaktualizowania (np. 'pacjent.md', 'tydzien.md').
        content: Pełna nowa treść pliku.

    Returns:
        Słownik z potwierdzeniem lub błędem.
    """
    if filename in FORBIDDEN:
        return {"error": f"Plik {filename} jest chroniony i nie może być zmieniony."}
    if "/" in filename or "\\" in filename:
        return {"error": "Nieprawidłowa nazwa pliku."}
    path = DATA_DIR / filename
    path.write_text(content, encoding="utf-8")
    return {"ok": True, "filename": filename}
