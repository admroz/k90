"""Narzędzia do pobierania wyników badań laboratoryjnych."""

from .db import get_conn, rows_to_list


def get_lab_results(category: str = None, test_name: str = None) -> list[dict]:
    """Pobiera wyniki badań laboratoryjnych.

    Args:
        category: Opcjonalny filtr kategorii (np. 'glukoza', 'lipidy', 'witaminy', 'nerki').
        test_name: Opcjonalny filtr nazwy konkretnego badania (np. 'HbA1c', 'LDL').

    Returns:
        Lista wyników: data, kategoria, badanie, wynik, jednostka, norma, ocena.
    """
    with get_conn() as conn:
        if category and test_name:
            rows = conn.execute(
                """SELECT data, kategoria, badanie, wynik, jednostka,
                          norma_min, norma_max, ocena, uwagi
                   FROM wyniki_lab
                   WHERE kategoria = ? AND badanie LIKE ?
                   ORDER BY data DESC, kategoria, badanie""",
                (category, f"%{test_name}%")
            ).fetchall()
        elif category:
            rows = conn.execute(
                """SELECT data, kategoria, badanie, wynik, jednostka,
                          norma_min, norma_max, ocena, uwagi
                   FROM wyniki_lab
                   WHERE kategoria = ?
                   ORDER BY data DESC, badanie""",
                (category,)
            ).fetchall()
        elif test_name:
            rows = conn.execute(
                """SELECT data, kategoria, badanie, wynik, jednostka,
                          norma_min, norma_max, ocena, uwagi
                   FROM wyniki_lab
                   WHERE badanie LIKE ?
                   ORDER BY data DESC""",
                (f"%{test_name}%",)
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT data, kategoria, badanie, wynik, jednostka,
                          norma_min, norma_max, ocena, uwagi
                   FROM wyniki_lab
                   ORDER BY data DESC, kategoria, badanie"""
            ).fetchall()
    return rows_to_list(rows)
