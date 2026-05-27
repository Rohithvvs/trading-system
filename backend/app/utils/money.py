from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Any


PRICE_QUANT = Decimal("0.01")
QTY_QUANT = Decimal("0.00000001")
PNL_QUANT = Decimal("0.01")


def dec(value: Any, default: Decimal | None = None) -> Decimal:
    if value is None:
        if default is not None:
            return default
        raise ValueError("Decimal value cannot be None")
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        if default is not None:
            return default
        raise ValueError(f"Invalid decimal value: {value!r}") from exc


def q_price(value: Any) -> Decimal:
    return dec(value).quantize(PRICE_QUANT, rounding=ROUND_HALF_UP)


def q_qty(value: Any) -> Decimal:
    return dec(value).quantize(QTY_QUANT, rounding=ROUND_HALF_UP)


def q_pnl(value: Any) -> Decimal:
    return dec(value).quantize(PNL_QUANT, rounding=ROUND_HALF_UP)


def as_float(value: Any) -> float:
    return float(dec(value, Decimal("0")))

