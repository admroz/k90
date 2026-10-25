"""Narzędzia do odczytu i aktualizacji plików danych pacjenta."""

from patient_documents import DOCUMENT_NAMES, get_document, write_document

# Optional explicit override retained for callers/tests; default is dynamic config.
DATA_DIR = None

ALLOWED_FILES = set(DOCUMENT_NAMES)
FORBIDDEN = {"system_prompt.md"}


def _validate_filename(filename: str) -> str | None:
    if filename in FORBIDDEN:
        return f"Plik {filename} jest chroniony i nie może być użyty."
    if "/" in filename or "\\" in filename:
        return "Nieprawidłowa nazwa pliku."
    if filename not in ALLOWED_FILES:
        allowed = ", ".join(sorted(ALLOWED_FILES))
        return f"Dozwolone pliki: {allowed}."
    return None


def read_patient_file(filename: str) -> dict:
    """Wczytuje plik danych pacjenta (pacjent.md, wywiad.md, analiza.md, dieta.md, tydzien.md).

    Args:
        filename: Nazwa pliku do odczytania.

    Returns:
        Słownik z kluczem 'content' (treść pliku) lub 'error'.
    """
    error = _validate_filename(filename)
    if error:
        return {"error": error}
    try:
        document = get_document(filename, data_dir=DATA_DIR)
    except (ValueError, OSError) as exc:
        return {"error": str(exc)}
    if document is None:
        return {"error": f"Plik {filename} nie istnieje."}
    return {"filename": filename, "content": document["content"]}


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
    error = _validate_filename(filename)
    if error:
        return {"error": error}
    try:
        write_document(filename, content, data_dir=DATA_DIR)
    except (ValueError, OSError) as exc:
        return {"error": str(exc)}
    return {"ok": True, "filename": filename}
