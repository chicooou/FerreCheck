"""
Motor financiero y lógica de negocio para FerreCheck.
Maneja las reglas de límites de compra, saldo disponible, semáforo y utilidades.
"""

from typing import Dict, List, Any
from config import ESTRATEGIAS, TOPE_SEGURIDAD_PORCENTAJE

def calcular_gastos_totales(gastos: Dict[str, float]) -> float:
    """Suma todos los gastos fijos configurados."""
    return sum(gastos.values())

def calcular_saldo_disponible(ventas: float, gastos_totales: float) -> float:
    """Calcula el dinero disponible libre tras pagar todos los gastos fijos."""
    return max(0.0, ventas - gastos_totales)

def calcular_limite_compra(ventas: float, gastos_totales: float, estrategia_key: str) -> Dict[str, Any]:
    """
    Calcula el límite de compra recomendado según la estrategia y el saldo disponible.
    Aplica la regla de prioridad de gastos y ajuste automático de seguridad.
    """
    estrategia = ESTRATEGIAS.get(estrategia_key, ESTRATEGIAS["balance"])
    porcentaje_estrategia = estrategia["porcentaje"]
    
    # Límite sugerido basado en ventas
    limite_sugerido = ventas * porcentaje_estrategia
    
    # Saldo disponible tras gastos fijos
    # (El cálculo de disponible_tras_gastos es el tope máximo absoluto)
    saldo_disponible = ventas - gastos_totales
    
    fue_ajustado = False
    limite_real = limite_sugerido
    
    if saldo_disponible <= 0:
        limite_real = 0.0
        fue_ajustado = True
    elif limite_sugerido > saldo_disponible:
        # Se excede el saldo tras gastos fijos, se ajusta al 90% del saldo real disponible
        limite_real = saldo_disponible * TOPE_SEGURIDAD_PORCENTAJE
        fue_ajustado = True
        
    return {
        "limite_sugerido": max(0.0, limite_sugerido),
        "limite_real": max(0.0, limite_real),
        "fue_ajustado": fue_ajustado,
        "saldo_disponible": max(0.0, saldo_disponible),
        "porcentaje_estrategia": porcentaje_estrategia
    }

def calcular_total_compras(compras: List[Dict[str, Any]]) -> float:
    """Calcula el total de compras acumuladas registradas."""
    return sum(compra["monto"] for compra in compras)

def calcular_utilidad_estimada(ventas: float, gastos_totales: float, total_compras: float) -> float:
    """
    Calcula la utilidad operativa estimada del período.
    Ventas - Gastos Fijos - Compras Totales realizadas.
    """
    return ventas - gastos_totales - total_compras

def calcular_consumo_presupuesto(total_compras: float, limite_real: float) -> float:
    """Retorna el porcentaje de presupuesto consumido (0-100%)."""
    if limite_real <= 0:
        return 100.0 if total_compras > 0 else 0.0
    return min(100.0, (total_compras / limite_real) * 100.0)

def obtener_estado_semaforo(consumo_pct: float) -> Dict[str, str]:
    """
    Determina el color, emoji y mensaje según el consumo del límite de compra.
    """
    if consumo_pct <= 50.0:
        return {
            "color": "🟢 Verde",
            "hex": "#09AB3B",
            "emoji": "✅",
            "mensaje": "Presupuesto saludable. Puedes seguir comprando con normalidad.",
            "status": "success"
        }
    elif consumo_pct <= 75.0:
        return {
            "color": "🟡 Amarillo",
            "hex": "#FFC107",
            "emoji": "⚠️",
            "mensaje": "Consumo moderado. Evalúa prioridades antes de nuevas compras.",
            "status": "warning"
        }
    elif consumo_pct <= 90.0:
        return {
            "color": "🟠 Naranja",
            "hex": "#FF9800",
            "emoji": "🚨",
            "mensaje": "Alerta. Te estás acercando al límite de compra mensual permitido.",
            "status": "warning"
        }
    else:
        return {
            "color": "🔴 Rojo",
            "hex": "#FF4B4B",
            "emoji": "🛑",
            "mensaje": "¡Crítico! Has alcanzado o superado el límite de compra establecido para evitar descapitalización.",
            "status": "error"
        }
