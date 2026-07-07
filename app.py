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
from modules.daily_sales import render_daily_sale_form, render_daily_sales_table, render_sales_kpis, render_analytics_panel
from modules.export import render_export_button
from modules.invoice_ui import render_invoice_tab
from modules.tab_buying_intel import render_buying_intel_tab
from dotenv import load_dotenv

# Cargar variables de entorno del archivo .env
load_dotenv()

from modules.history import (
    render_history_view,
    render_close_period_button,
    load_current_period,
    save_current_period,
    load_history
)
from modules.engine import (
    calcular_gastos_totales,
    calcular_limite_compra,
    calcular_total_compras,
    calcular_utilidad_estimada,
    calcular_utilidad_por_modalidad,
    calcular_consumo_presupuesto,
    calcular_proyeccion_futura,
    evaluar_madurez_historial
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

# Garantizar que los nuevos campos existan en el período actual
if "deudas_heredadas" not in p:
    p["deudas_heredadas"] = []
if "deudas_futuras" not in p:
    p["deudas_futuras"] = []

# 4. Procesamiento de Cálculos Financieros (Core Engine)
gastos_totales = calcular_gastos_totales(p["gastos"])
res_limite = calcular_limite_compra(p["ventas"], gastos_totales, p["estrategia"])

limite_real = res_limite["limite_real"]
total_compras = calcular_total_compras(p["compras"])

# Utilidad segmentada por modalidad de pago (nueva lógica)
util_modalidad = calcular_utilidad_por_modalidad(
    ventas=p["ventas"],
    gastos_totales=gastos_totales,
    compras=p["compras"],
    deudas_heredadas=p.get("deudas_heredadas", []),
    mes_actual=p["mes"],
    ano_actual=p["ano"]
)

# Calcular proyecciones futuras
proyeccion_futura = calcular_proyeccion_futura(
    util_modalidad=util_modalidad,
    deudas_futuras=p.get("deudas_futuras", []),
    ventas_diarias=p.get("ventas_diarias", []),
    ventas_sidebar=p["ventas"],
    gastos=p["gastos"],
    estrategia=p["estrategia"],
    mes_actual=p["mes"],
    ano_actual=p["ano"]
)

# Cargar historial y evaluar madurez para promedio histórico
historial = load_history()
madurez_historial = evaluar_madurez_historial(historial)

consumo_pct = calcular_consumo_presupuesto(total_compras, limite_real)

calc_results = {
    "gastos_totales": gastos_totales,
    "limite_sugerido": res_limite["limite_sugerido"],
    "limite_real": limite_real,
    "fue_ajustado": res_limite["fue_ajustado"],
    "saldo_disponible": res_limite["saldo_disponible"],
    "total_compras": total_compras,
    "utilidad_estimada": calcular_utilidad_estimada(p["ventas"], gastos_totales, total_compras),  # Legacy
    "utilidad_real": util_modalidad["utilidad_real"],  # Nueva métrica correcta
    "util_modalidad": util_modalidad,
    "consumo_pct": consumo_pct,
    "proyeccion_futura": proyeccion_futura,
    "madurez_historial": madurez_historial
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

# 6. Renderizar Pestañas Principales (Navegación Robusta con Session State)
st.markdown(" ")  # Spacer

if "active_tab" not in st.session_state:
    st.session_state.active_tab = "dashboard"

tabs_info = [
    ("📊 Cuadro de Mando", "dashboard"),
    ("📝 Registro de Compras", "compras"),
    ("📈 Caja Diaria", "ventas"),
    ("📜 Historial Multi-Período", "historial"),
    ("🛒 Inteligencia de Compras", "intel"),
    ("📸 Factura → Odoo", "invoice")
]

# Botones de navegación horizontales
cols_nav = st.columns(6)
for idx, (label, tab_name) in enumerate(tabs_info):
    with cols_nav[idx]:
        is_active = (st.session_state.active_tab == tab_name)
        if st.button(
            label, 
            key=f"nav_btn_{tab_name}", 
            type="primary" if is_active else "secondary", 
            use_container_width=True
        ):
            st.session_state.active_tab = tab_name
            st.rerun()

st.write("---")

active_tab = st.session_state.active_tab

if active_tab == "dashboard":
    render_dashboard(p, calc_results)

elif active_tab == "compras":
    col_form, col_tabla = st.columns([1, 2], gap="large")
    with col_form:
        render_purchase_form(p, limite_real)
    with col_tabla:
        render_purchase_table(p, limite_real)
        st.write("---")
        render_export_button(p)

elif active_tab == "ventas":
    render_sales_kpis(p)
    col_form_v, col_tabla_v = st.columns([1, 2], gap="large")
    with col_form_v:
        render_daily_sale_form(p)
    with col_tabla_v:
        render_daily_sales_table(p)
    render_analytics_panel(p)

elif active_tab == "historial":
    render_history_view()

elif active_tab == "intel":
    render_buying_intel_tab()

elif active_tab == "invoice":
    render_invoice_tab()

# 7. Guardado Automático (Autosave en disco al finalizar cada render)
save_current_period(p)

# 8. Pie de Página (Footer)
st.markdown(
    """
    <div style="text-align: center; margin-top: 50px; padding: 20px; border-top: 1px solid rgba(255,255,255,0.05); color: #5F738C; font-size: 13px;">
        FerreCheck — Diseñado para el control de flujo de caja y compras operativas de ferreterías. Versión 2.0.
    </div>
    """,
    unsafe_allow_html=True
)
