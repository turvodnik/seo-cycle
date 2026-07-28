"""Единая CTR-кривая «позиция → ожидаемый CTR».

Источник истины для triggers-eval (сортировка по потенциалу, сниппет-правила).
Значения совпадают с DEFAULT_CTR_CURVE в seo-forecast.py (тот дополнительно
поддерживает project-override через kpi.ctr_curve; при изменении кривой
обновлять оба места до консолидации в v2.1).
"""
from __future__ import annotations

DEFAULT_CTR_CURVE: dict[int, float] = {
    1: 0.28, 2: 0.15, 3: 0.10, 4: 0.07, 5: 0.05,
    6: 0.04, 7: 0.03, 8: 0.025, 9: 0.02, 10: 0.018,
}
CTR_11_20: float = 0.01
CTR_BEYOND: float = 0.002


def expected_ctr(position: float | None, curve: dict[int, float] | None = None) -> float:
    """Ожидаемый CTR для средней позиции (bucket = round(position))."""
    if position is None or position <= 0:
        return CTR_BEYOND
    table = curve or DEFAULT_CTR_CURVE
    bucket = int(round(position))
    if bucket in table:
        return table[bucket]
    if 11 <= bucket <= 20:
        return CTR_11_20
    return CTR_BEYOND
