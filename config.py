"""
Configuración global y constantes de negocio de FerreCheck.
"""

# Configuración de Moneda e Identidad
MONEDA_SIMBOLO = "Q"
MONEDA_CODIGO = "GTQ"

# Constantes del Negocio (Estrategias de Compra)
ESTRATEGIAS = {
    "reducir": {
        "nombre": "🔻 Reducir Inventario",
        "porcentaje": 0.50,
        "descripcion": "Límite de compra = 50% de las ventas. Recomendado para liberar efectivo o corregir sobrestock.",
        "color": "#FF4B4B",
    },
    "balance": {
        "nombre": "⚖️ Mantener Balance",
        "porcentaje": 0.70,
        "descripcion": "Límite de compra = 70% de las ventas. Recomendado para mantener un ritmo operativo saludable.",
        "color": "#00C0F2",
    },
    "aumentar": {
        "nombre": "📈 Aumentar Inventario",
        "porcentaje": 0.85,
        "descripcion": "Límite de compra = 85% de las ventas. Recomendado para temporadas altas o compras de oportunidad.",
        "color": "#09AB3B",
    }
}

# Límite Máximo de Seguridad
# Si el límite sugerido supera el saldo disponible, el límite se ajusta al 90% del saldo disponible tras gastos fijos.
TOPE_SEGURIDAD_PORCENTAJE = 0.90

# Constantes de Tiempo
MESES = {
    1: "Enero",
    2: "Febrero",
    3: "Marzo",
    4: "Abril",
    5: "Mayo",
    6: "Junio",
    7: "Julio",
    8: "Agosto",
    9: "Septiembre",
    10: "Octubre",
    11: "Noviembre",
    12: "Diciembre"
}

ANOS_RANGO = [2025, 2026, 2027, 2028, 2029, 2030]

def get_month_name(month_num: int) -> str:
    """Retorna el nombre del mes en español."""
    return MESES.get(month_num, "Desconocido")

def format_currency(value: float) -> str:
    """Formatea un valor numérico como moneda (ej: Q 150,000.00)."""
    return f"{MONEDA_SIMBOLO} {value:,.2f}"

def format_currency_clean(value: float) -> str:
    """Formatea un valor numérico como moneda, ocultando decimales si son .00 (ej: Q 150,000)."""
    if value == int(value):
        return f"{MONEDA_SIMBOLO} {int(value):,}"
    return f"{MONEDA_SIMBOLO} {value:,.2f}"

