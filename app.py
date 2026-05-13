"""
FerreCheck — Liquidez y Compras
Entrypoint principal de la WebApp.
Integración completa de todas las funcionalidades, módulos financieros y autosave.
"""

import streamlit as st
import datetime
import os
from modules.sidebar import render_sidebar
from modules.dashboard import render_dashboard
from modules.purchases import render_purchase_form, render_purchase_table
from modules.export import render_export_button
from modules.history import (
    render_history_view,
    render_close_period_button,
    load_current_period,
    save_current_period
)
from modules.engine import (
    calcular_gastos_totales,
    calcular_limite_compra,
    calcular_total_compras,
    calcular_utilidad_estimada,
    calcular_consumo_presupuesto
)

# 1. Configuración de página
st.set_page_config(
    page_title="FerreCheck — Liquidez y Compras",
    page_icon="🔧",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Cargar e inyectar CSS Premium
css_path = os.path.join("assets", "style.css")
if os.path.exists(css_path):
    with open(css_path, "r", encoding="utf-8") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# 2. Inicializar Estado de la Sesión (Cargando autosave si existe)
if "periodo_actual" not in st.session_state:
    st.session_state.periodo_actual = load_current_period()

# 3. Renderizar Barra Lateral (Sidebar)
p = render_sidebar()

# 4. Procesamiento de Cálculos Financieros (Core Engine)
gastos_totales = calcular_gastos_totales(p["gastos"])
res_limite = calcular_limite_compra(p["ventas"], gastos_totales, p["estrategia"])

limite_real = res_limite["limite_real"]
total_compras = calcular_total_compras(p["compras"])
utilidad_estimada = calcular_utilidad_estimada(p["ventas"], gastos_totales, total_compras)
consumo_pct = calcular_consumo_presupuesto(total_compras, limite_real)

calc_results = {
    "gastos_totales": gastos_totales,
    "limite_sugerido": res_limite["limite_sugerido"],
    "limite_real": limite_real,
    "fue_ajustado": res_limite["fue_ajustado"],
    "saldo_disponible": res_limite["saldo_disponible"],
    "total_compras": total_compras,
    "utilidad_estimada": utilidad_estimada,
    "consumo_pct": consumo_pct
}

# Botón de Cierre de Período en la parte inferior del Sidebar
render_close_period_button(p)

# 5. Cabecera Principal de la Aplicación
st.markdown(
    """
    <div style="display: flex; align-items: center; gap: 15px; margin-bottom: 5px;">
        <span style="font-size: 40px;">🔧</span>
        <h1 style="margin: 0; font-size: 36px; font-weight: 700;">FerreCheck</h1>
    </div>
    <p style="color: #8C9CAE; font-size: 16px; margin-top: 0; margin-bottom: 25px;">
        Control operativo de Liquidez, Gastos Fijos y Semáforo de Compras Mensuales.
    </p>
    """, 
    unsafe_allow_html=True
)

# 6. Renderizar Pestañas Principales (Tabs)
tab_dashboard, tab_compras, tab_historial = st.tabs([
    "📊 Cuadro de Mando (Dashboard)", 
    "📝 Registro de Compras", 
    "📜 Historial Multi-Período"
])

with tab_dashboard:
    render_dashboard(p, calc_results)

with tab_compras:
    col_form, col_tabla = st.columns([1, 2], gap="large")
    
    with col_form:
        render_purchase_form(p, limite_real)
        
    with col_tabla:
        render_purchase_table(p, limite_real)
        st.write("---")
        render_export_button(p)

with tab_historial:
    render_history_view()

# 7. Guardado Automático (Autosave en disco al finalizar cada render)
save_current_period(p)

# 8. Pie de Página (Footer)
st.markdown(
    """
    <div style="text-align: center; margin-top: 50px; padding: 20px; border-top: 1px solid rgba(255,255,255,0.05); color: #5F738C; font-size: 13px;">
        FerreCheck — Diseñado para el control de flujo de caja y compras operativas de ferreterías. Versión 1.0.
    </div>
    """, 
    unsafe_allow_html=True
)
