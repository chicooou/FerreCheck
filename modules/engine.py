"""
Motor financiero y lógica de negocio para FerreCheck.
Maneja las reglas de límites de compra, saldo disponible, semáforo y utilidades.
v2: Incorpora cálculo de Utilidad Real segmentada por modalidad de pago (Contado vs. Crédito)
    y soporte para deudas heredadas de períodos anteriores.
"""

import datetime
from typing import Dict, List, Any, Tuple

from config import ESTRATEGIAS, TOPE_SEGURIDAD_PORCENTAJE

# Mapa de días de crédito por modalidad
DIAS_CREDITO: Dict[str, int] = {
    "Contado": 0,
    "Crédito 30 días": 30,
    "Crédito 45 días": 45,
    "Crédito 60 días": 60,
}


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
    saldo_disponible = ventas - gastos_totales

    fue_ajustado = False
    limite_real = limite_sugerido

    if saldo_disponible <= 0:
        limite_real = 0.0
        fue_ajustado = True
    elif limite_sugerido > saldo_disponible:
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
    """Calcula el total de compras acumuladas registradas (todos los modos de pago)."""
    return sum(compra["monto"] for compra in compras)


def calcular_utilidad_estimada(ventas: float, gastos_totales: float, total_compras: float) -> float:
    """
    [LEGACY] Calcula la utilidad operativa simple del período.
    Ventas - Gastos Fijos - Compras Totales (sin distinguir modalidad).
    Mantenida por compatibilidad con el historial existente.
    """
    return ventas - gastos_totales - total_compras


# ─────────────────────────────────────────────────────────────────────────────
# NUEVAS FUNCIONES: Utilidad Real por Modalidad de Pago
# ─────────────────────────────────────────────────────────────────────────────

def calcular_fecha_vencimiento(fecha_compra_str: str, modalidad: str) -> Tuple[int, int]:
    """
    Calcula el mes y año exacto en que vence una compra a crédito.
    Retorna (mes_vencimiento, año_vencimiento).
    """
    dias = DIAS_CREDITO.get(modalidad, 0)
    fecha = datetime.datetime.strptime(fecha_compra_str, "%Y-%m-%d")

    if dias == 0:
        return (fecha.month, fecha.year)

    fecha_vencimiento = fecha + datetime.timedelta(days=dias)
    return (fecha_vencimiento.month, fecha_vencimiento.year)


def calcular_distancia_meses(mes_origen: int, ano_origen: int, mes_destino: int, ano_destino: int) -> int:
    """Calcula la distancia en meses entre dos fechas (mes/año)."""
    return (ano_destino - ano_origen) * 12 + (mes_destino - mes_origen)


def calcular_utilidad_por_modalidad(
    ventas: float,
    gastos_totales: float,
    compras: List[Dict[str, Any]],
    deudas_heredadas: List[Dict[str, Any]],
    mes_actual: int,
    ano_actual: int
) -> Dict[str, Any]:
    """
    Calcula la Utilidad REAL del mes, segmentando el impacto financiero
    de las compras según cuándo vence cada modalidad de pago.

    Reglas:
    - Contado → Impacta ESTE mes siempre.
    - Crédito X días → Se calcula la fecha de vencimiento exacta.
      Si cae en ESTE mes → impacta la utilidad actual.
      Si cae en mes futuro → es un "compromiso futuro" (no resta ahora).
    - Deudas Heredadas → Créditos de meses anteriores que vencen ESTE mes.
    """
    egreso_contado = 0.0
    egreso_credito_vencido_hoy = 0.0
    compromisos_mes_siguiente = 0.0
    compromisos_mes_2_plus = 0.0
    detalle_compromisos_futuros: List[Dict[str, Any]] = []

    for c in compras:
        modalidad = c.get("modalidad", "Contado")
        if modalidad == "Contado":
            egreso_contado += c["monto"]
        else:
            mes_venc, ano_venc = calcular_fecha_vencimiento(c["fecha"], modalidad)
            dist = calcular_distancia_meses(mes_actual, ano_actual, mes_venc, ano_venc)

            if dist <= 0:
                # Venció en este mes o en un mes pasado (ya exigible)
                egreso_credito_vencido_hoy += c["monto"]
            elif dist == 1:
                compromisos_mes_siguiente += c["monto"]
                detalle_compromisos_futuros.append({
                    "monto": c["monto"],
                    "proveedor": c.get("proveedor", "?"),
                    "modalidad": modalidad,
                    "fecha_compra": c["fecha"],
                    "mes_vencimiento": mes_venc,
                    "ano_vencimiento": ano_venc,
                    "distancia_meses": dist
                })
            else:
                compromisos_mes_2_plus += c["monto"]
                detalle_compromisos_futuros.append({
                    "monto": c["monto"],
                    "proveedor": c.get("proveedor", "?"),
                    "modalidad": modalidad,
                    "fecha_compra": c["fecha"],
                    "mes_vencimiento": mes_venc,
                    "ano_vencimiento": ano_venc,
                    "distancia_meses": dist
                })

    # Deudas heredadas de meses anteriores que vencen este mes
    egreso_deudas_heredadas = sum(d["monto"] for d in deudas_heredadas)

    egreso_real_mes = egreso_contado + egreso_credito_vencido_hoy + egreso_deudas_heredadas
    utilidad_real = ventas - gastos_totales - egreso_real_mes

    return {
        "utilidad_real": utilidad_real,
        "egreso_contado": egreso_contado,
        "egreso_credito_vencido": egreso_credito_vencido_hoy,
        "egreso_deudas_heredadas": egreso_deudas_heredadas,
        "egreso_real_mes": egreso_real_mes,
        "compromisos_mes_siguiente": compromisos_mes_siguiente,
        "compromisos_mes_2_plus": compromisos_mes_2_plus,
        "compromisos_total_futuro": compromisos_mes_siguiente + compromisos_mes_2_plus,
        "detalle_compromisos_futuros": detalle_compromisos_futuros,
        "deudas_heredadas": deudas_heredadas,
    }


def resolver_deudas_para_herencia(
    compras: List[Dict[str, Any]],
    mes_actual: int,
    ano_actual: int
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Al cerrar un período, clasifica todas las compras a crédito en:
    - deudas_para_mes_siguiente: vencen en Mes+1 (se heredan como deudas activas)
    - deudas_para_meses_futuros: vencen en Mes+2 o después (se guardan como cola)

    Retorna un dict con ambas listas listas para ser inyectadas en el nuevo período.
    """
    next_month = mes_actual + 1
    next_year = ano_actual
    if next_month > 12:
        next_month = 1
        next_year += 1

    deudas_heredadas_directo: List[Dict[str, Any]] = []
    deudas_futuras_cola: List[Dict[str, Any]] = []

    for c in compras:
        modalidad = c.get("modalidad", "Contado")
        if modalidad == "Contado":
            continue  # Ya impactó este mes, no se hereda

        mes_venc, ano_venc = calcular_fecha_vencimiento(c["fecha"], modalidad)
        dist = calcular_distancia_meses(mes_actual, ano_actual, mes_venc, ano_venc)

        deuda_base = {
            "id": c.get("id", ""),
            "monto": c["monto"],
            "proveedor": c.get("proveedor", "?"),
            "origen_mes": mes_actual,
            "origen_ano": ano_actual,
            "modalidad_original": modalidad,
            "fecha_compra": c["fecha"],
            "mes_vencimiento": mes_venc,
            "ano_vencimiento": ano_venc,
            "postergada": False,
            "veces_postergada": 0
        }

        if dist == 1:
            # Vence exactamente el mes siguiente → deuda heredada activa
            deudas_heredadas_directo.append(deuda_base)
        elif dist >= 2:
            # Vence más adelante → cola de deudas futuras
            deudas_futuras_cola.append(deuda_base)

    return {
        "deudas_heredadas": deudas_heredadas_directo,
        "deudas_futuras": deudas_futuras_cola
    }


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
