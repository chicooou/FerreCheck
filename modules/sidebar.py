"""
Módulo Sidebar para FerreCheck.
Maneja la entrada de configuración de gastos, ventas, estrategia y selección de período.
"""

import streamlit as st
import datetime
from config import ESTRATEGIAS, MESES, ANOS_RANGO, format_currency
from modules.engine import calcular_gastos_totales

def render_sidebar() -> dict:
    """
    Renderiza la barra lateral y retorna el estado del período activo.
    """
    st.sidebar.markdown("## ⚙️ Configuración")
    
    # 1. Selección de Período
    st.sidebar.subheader("📅 Período de Operación")
    p = st.session_state.periodo_actual
    
    col_ano, col_mes = st.sidebar.columns(2)
    with col_ano:
        ano = st.selectbox("Año", options=ANOS_RANGO, index=ANOS_RANGO.index(p["ano"]))
    with col_mes:
        mes = st.selectbox(
            "Mes", 
            options=list(MESES.keys()), 
            format_func=lambda x: MESES[x],
            index=list(MESES.keys()).index(p["mes"])
        )
        
    # Guardar cambios de período en el state si cambian
    if ano != p["ano"] or mes != p["mes"]:
        p["ano"] = ano
        p["mes"] = mes
        st.rerun()

    st.sidebar.write("---")

    # 2. Entradas Financieras
    st.sidebar.subheader("💰 Flujo Financiero")
    
    ventas = st.sidebar.number_input(
        "Ventas Mes Anterior",
        min_value=0.0,
        value=float(p["ventas"]),
        step=5000.0,
        format="%f",
        help="Las ventas totales reportadas el mes inmediato anterior (Base de cálculo)."
    )
    p["ventas"] = ventas

    # Gastos Fijos (en un expander para no saturar visualmente)
    with st.sidebar.expander("📋 Detalle de Gastos Fijos", expanded=True):
        planilla = st.number_input("Planilla / Sueldos", min_value=0.0, value=float(p["gastos"]["planilla"]), step=1000.0)
        renta = st.number_input("Renta / Alquiler", min_value=0.0, value=float(p["gastos"]["renta"]), step=500.0)
        luz = st.number_input("Luz y Agua", min_value=0.0, value=float(p["gastos"]["luz"]), step=100.0)
        otros = st.number_input("Otros Gastos Fijos", min_value=0.0, value=float(p["gastos"]["otros"]), step=500.0)
        
        # Actualizar valores
        p["gastos"]["planilla"] = planilla
        p["gastos"]["renta"] = renta
        p["gastos"]["luz"] = luz
        p["gastos"]["otros"] = otros
        
        gastos_totales = calcular_gastos_totales(p["gastos"])
        st.markdown(f"**Total Gastos Fijos:**\n `{format_currency(gastos_totales)}`")

    st.sidebar.write("---")

    # 3. Estrategia de Compras
    st.sidebar.subheader("🎯 Estrategia de Inventario")
    
    estrategia_options = list(ESTRATEGIAS.keys())
    estrategia_actual = p["estrategia"]
    
    estrategia = st.sidebar.radio(
        "Seleccione la Estrategia:",
        options=estrategia_options,
        format_func=lambda x: ESTRATEGIAS[x]["nombre"],
        index=estrategia_options.index(estrategia_actual),
        help="Determina el porcentaje de las ventas destinado a compras de inventario."
    )
    p["estrategia"] = estrategia
    
    # Mostrar descripción de la estrategia seleccionada de manera elegante
    st.sidebar.info(ESTRATEGIAS[estrategia]["descripcion"])
    
    # Retornar período actualizado
    return p
