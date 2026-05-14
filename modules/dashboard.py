"""
Módulo Dashboard de FerreCheck.
Presenta los KPIs principales, alertas inteligentes, la barra de progreso del semáforo
y el nuevo panel ejecutivo de Proyección de Desembolso de Efectivo (Crédito).
"""

import streamlit as st
from config import format_currency, ESTRATEGIAS
from modules.engine import obtener_estado_semaforo

def render_kpi_card(titulo: str, valor: str, icono: str, ayuda: str = "") -> str:
    """Retorna código HTML para una tarjeta KPI premium."""
    tooltip = f'title="{ayuda}"' if ayuda else ""
    return f"""
    <div class="kpi-container" {tooltip}>
        <div class="kpi-title">{icono} {titulo}</div>
        <div class="kpi-value">{valor}</div>
    </div>
    """

def render_dashboard(p: dict, calc_results: dict):
    """
    Renderiza las 4 métricas clave, el semáforo financiero y la proyección de flujo.
    """
    # 1. Tarjetas KPI
    st.markdown("### 📊 Estado de Flujo de Caja")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown(
            render_kpi_card(
                "Ventas", 
                format_currency(p["ventas"]), 
                "💵", 
                "Ventas del mes inmediato anterior."
            ), 
            unsafe_allow_html=True
        )
        
    with col2:
        st.markdown(
            render_kpi_card(
                "Gastos Fijos", 
                format_currency(calc_results["gastos_totales"]), 
                "📋", 
                "Suma de Planilla, Renta, Luz y Otros gastos recurrentes."
            ), 
            unsafe_allow_html=True
        )
        
    with col3:
        limite_texto = format_currency(calc_results["limite_real"])
        if calc_results["fue_ajustado"]:
            limite_texto += " ⚠️"
        st.markdown(
            render_kpi_card(
                "Límite de Compra", 
                limite_texto, 
                "🎯", 
                "Presupuesto máximo de compras asignado al mes actual."
            ), 
            unsafe_allow_html=True
        )
        
    with col4:
        st.markdown(
            render_kpi_card(
                "Utilidad Estimada", 
                format_currency(calc_results["utilidad_estimada"]), 
                "📈" if calc_results["utilidad_estimada"] >= 0 else "📉", 
                "Ventas menos Gastos Fijos y Compras registradas."
            ), 
            unsafe_allow_html=True
        )

    st.write("")

    # 2. Alertas Inteligentes de Seguridad Financiera
    if calc_results["fue_ajustado"]:
        if calc_results["saldo_disponible"] <= 0:
            st.error(
                f"🚨 **¡Bloqueo de Emergencia por Liquidez!** "
                f"El saldo disponible tras gastos fijos es de **{format_currency(calc_results['saldo_disponible'])}**. "
                f"No puedes registrar compras para este período ya que no hay suficiente margen para cubrir tus costos fijos esenciales."
            )
        else:
            st.warning(
                f"⚠️ **Ajuste de Seguridad Activo:** El límite de compra sugerido original de **{format_currency(calc_results['limite_sugerido'])}** "
                f"ha sido reajustado al 90% del saldo real disponible para garantizar la cobertura de tus gastos fijos. "
                f"Límite Seguro de Compra: **{format_currency(calc_results['limite_real'])}**."
            )

    # 3. Semáforo y Barra de Progreso Visual
    st.markdown("### 🚦 Semáforo de Consumo Presupuestario")
    
    consumo_pct = calc_results["consumo_pct"]
    total_compras = calc_results["total_compras"]
    limite_real = calc_results["limite_real"]
    semaforo = obtener_estado_semaforo(consumo_pct)
    
    st.markdown(
        f"""
        <div class="progress-container">
            <div class="progress-header">
                <span class="progress-title">Compras del Mes: <b>{format_currency(total_compras)}</b> de un límite de <b>{format_currency(limite_real)}</b></span>
                <span class="progress-percentage" style="color: {semaforo['hex']};">{consumo_pct:.1f}% Consumido</span>
            </div>
            <div style="background-color: rgba(255,255,255,0.1); border-radius: 10px; height: 16px; width: 100%; overflow: hidden;">
                <div style="background-color: {semaforo['hex']}; width: {consumo_pct}%; height: 100%; border-radius: 10px; transition: width 0.5s ease-in-out;"></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    mensaje_alerta = f"**Estado Presupuesto: {semaforo['emoji']} {semaforo['color']}** - {semaforo['mensaje']}"
    if semaforo["status"] == "success":
        st.success(mensaje_alerta)
    elif semaforo["status"] == "warning":
        st.warning(mensaje_alerta)
    elif semaforo["status"] == "error":
        st.error(mensaje_alerta)

    # 4. Proyección Ejecutivo de Desembolso de Efectivo (Crédito)
    st.write("---")
    st.markdown("### 🔮 Proyección de Desembolso de Efectivo (Flujo de Caja Futuro)")
    st.caption("Proyección ejecutiva de en qué momento saldrá el dinero de la cuenta bancaria según los plazos de crédito otorgados por los proveedores.")
    
    tot_contado = sum(c["monto"] for c in p["compras"] if c.get("modalidad") == "Contado")
    tot_30 = sum(c["monto"] for c in p["compras"] if c.get("modalidad") == "Crédito 30 días")
    tot_45 = sum(c["monto"] for c in p["compras"] if c.get("modalidad") == "Crédito 45 días")
    tot_60 = sum(c["monto"] for c in p["compras"] if c.get("modalidad") == "Crédito 60 días")
    
    col_p1, col_p2, col_p3, col_p4 = st.columns(4)
    with col_p1:
        st.markdown(render_kpi_card("Contado / Inmediato", format_currency(tot_contado), "💵", "Efectivo que sale de la cuenta bancaria este mismo mes."), unsafe_allow_html=True)
    with col_p2:
        st.markdown(render_kpi_card("Crédito a 30 días", format_currency(tot_30), "🗓️", "Cuentas por pagar que vencen el próximo mes (Mes + 1)."), unsafe_allow_html=True)
    with col_p3:
        st.markdown(render_kpi_card("Crédito a 45 días", format_currency(tot_45), "🗓️", "Cuentas por pagar que vencen en mes y medio."), unsafe_allow_html=True)
    with col_p4:
        st.markdown(render_kpi_card("Crédito a 60 días", format_currency(tot_60), "🗓️", "Cuentas por pagar que vencen dentro de dos meses (Mes + 2)."), unsafe_allow_html=True)
