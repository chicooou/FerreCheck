"""
Módulo Dashboard de FerreCheck.
Presenta los KPIs principales, alertas inteligentes y la barra de progreso del semáforo.
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
    Renderiza las 4 métricas clave y el semáforo financiero.
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
        # Mostrar asterisco de advertencia si fue auto-ajustado por flujo de caja
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
    
    # Renderizar barra de progreso customizada con el color del semáforo
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

    # Mostrar alerta de estado de Streamlit según corresponda
    mensaje_alerta = f"**Estado Presupuesto: {semaforo['emoji']} {semaforo['color']}** - {semaforo['mensaje']}"
    if semaforo["status"] == "success":
        st.success(mensaje_alerta)
    elif semaforo["status"] == "warning":
        st.warning(mensaje_alerta)
    elif semaforo["status"] == "error":
        st.error(mensaje_alerta)
