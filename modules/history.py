"""
Módulo de Gestión de Historial y Copias de Seguridad para FerreCheck.
Permite cargar, guardar, cerrar períodos actuales, visualizar históricos y hacer copias de seguridad (.json).
"""

import streamlit as st
import json
import os
import pandas as pd
from config import format_currency, MESES, get_month_name, ESTRATEGIAS
from modules.engine import (
    calcular_gastos_totales,
    calcular_limite_compra,
    calcular_total_compras,
    calcular_utilidad_estimada
)

HISTORY_FILE = os.path.join("data", "history.json")

def load_history() -> dict:
    """Carga el historial desde el archivo JSON de forma segura."""
    if not os.path.exists(HISTORY_FILE):
        return {}
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_history(history: dict):
    """Guarda el historial en el archivo JSON."""
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)

def save_period(p: dict):
    """Guarda el período actual en el historial."""
    history = load_history()
    
    year_str = str(p["ano"])
    month_str = str(p["mes"])
    
    if year_str not in history:
        history[year_str] = {}
        
    history[year_str][month_str] = {
        "ventas": p["ventas"],
        "gastos": p["gastos"].copy(),
        "estrategia": p["estrategia"],
        "compras": p["compras"].copy()
    }
    
    save_history(history)

def render_history_view():
    """
    Muestra el historial completo de períodos cerrados de manera organizada.
    También integra la funcionalidad de copias de seguridad (Backup & Restore).
    """
    st.markdown("### 📜 Historial de Períodos Cerrados")
    history = load_history()
    
    # 1. Sección de Copia de Seguridad y Restauración (Backup & Restore)
    with st.expander("💾 Copia de Seguridad y Restauración (Sin Base de Datos)", expanded=False):
        col_backup, col_restore = st.columns(2, gap="medium")
        
        with col_backup:
            st.markdown("**📥 Descargar Respaldo**")
            st.write("Descarga una copia completa de tu historial local para guardarla en tu computadora o dispositivo.")
            if history:
                backup_data = json.dumps(history, indent=2, ensure_ascii=False)
                st.download_button(
                    label="📥 Descargar Archivo de Respaldo (.json)",
                    data=backup_data,
                    file_name="FerreCheck_Respaldo_Historial.json",
                    mime="application/json",
                    use_container_width=True
                )
            else:
                st.info("No hay datos históricos disponibles para respaldar todavía.")
                
        with col_restore:
            st.markdown("**📤 Restaurar Respaldo**")
            st.write("Sube un archivo de respaldo (.json) descargado previamente para restaurar tu historial instantáneamente.")
            uploaded_file = st.file_uploader("Subir archivo de respaldo (.json)", type=["json"], label_visibility="collapsed")
            
            if uploaded_file is not None:
                try:
                    uploaded_data = json.load(uploaded_file)
                    # Validación simple de estructura
                    if isinstance(uploaded_data, dict):
                        if st.button("🔄 Confirmar y Restaurar Datos", type="primary", use_container_width=True):
                            save_history(uploaded_data)
                            st.success("✅ Historial restaurado con éxito.")
                            st.rerun()
                    else:
                        st.error("⚠️ El formato del archivo de respaldo no es válido.")
                except Exception as e:
                    st.error(f"❌ Error al leer el archivo de respaldo: {str(e)}")

    st.write("---")

    # 2. Visualización de Períodos Históricos
    if not history:
        st.info("📂 No hay períodos archivados en el historial todavía. Cierra un período mensual en la barra lateral para registrarlo aquí.")
        return

    # Años disponibles ordenados de forma descendente (más recientes primero)
    years = sorted(list(history.keys()), reverse=True)
    
    # Crear pestañas por año
    tabs_years = st.tabs([f"Año {yr}" for yr in years])
    
    for i, yr in enumerate(years):
        with tabs_years[i]:
            months_data = history[yr]
            months_keys = sorted(list(months_data.keys()), key=int, reverse=True)
            
            for m_key in months_keys:
                m_data = months_data[m_key]
                m_num = int(m_key)
                m_name = get_month_name(m_num)
                
                # Cálculos para este mes histórico
                g_totales = calcular_gastos_totales(m_data["gastos"])
                total_c = calcular_total_compras(m_data["compras"])
                res_lim = calcular_limite_compra(m_data["ventas"], g_totales, m_data["estrategia"])
                utilidad = calcular_utilidad_estimada(m_data["ventas"], g_totales, total_c)
                
                estr_info = ESTRATEGIAS.get(m_data["estrategia"], ESTRATEGIAS["balance"])
                
                expander_label = f"📅 {m_name} {yr} | Compras: {format_currency(total_c)} / Límite: {format_currency(res_lim['limite_real'])}"
                
                with st.expander(expander_label):
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.markdown(f"**Ventas:**\n {format_currency(m_data['ventas'])}")
                    with col2:
                        st.markdown(f"**Gastos Fijos:**\n {format_currency(g_totales)}")
                    with col3:
                        st.markdown(
                            f"**Límite de Compra:**\n {format_currency(res_lim['limite_real'])} "
                            f"{'⚠️ (Ajustado)' if res_lim['fue_ajustado'] else '✅'}"
                        )
                    with col4:
                        st.markdown(f"**Utilidad Operativa:**\n {format_currency(utilidad)}")
                        
                    st.caption(f"Estrategia Aplicada: **{estr_info['nombre']}** ({int(estr_info['porcentaje']*100)}% de Ventas)")
                    
                    st.markdown("**Detalle de Compras:**")
                    if not m_data["compras"]:
                        st.write("No se registraron compras en este período.")
                    else:
                        df_hist = pd.DataFrame(m_data["compras"])
                        df_hist["Monto"] = df_hist["monto"].apply(format_currency)
                        df_hist["Fecha"] = pd.to_datetime(df_hist["fecha"]).dt.strftime("%d/%m/%Y")
                        df_hist = df_hist.rename(columns={"proveedor": "Proveedor", "nota": "Descripción"})
                        df_hist_visual = df_hist[["Fecha", "Proveedor", "Monto", "Descripción"]]
                        df_hist_visual.index = range(1, len(df_hist_visual) + 1)
                        st.dataframe(df_hist_visual, use_container_width=True)

def render_close_period_button(p: dict):
    """Renderiza la sección de cierre de período en el sidebar."""
    st.sidebar.markdown("---")
    st.sidebar.subheader("📦 Cierre de Período")
    
    with st.sidebar.expander("🔐 Cerrar Mes Actual", expanded=False):
        st.write("El cierre archivará las ventas, gastos y compras registradas para este período en el historial multi-período.")
        st.warning("⚠️ Esta acción no se puede deshacer.")
        
        confirmado = st.checkbox("Confirmar cierre de período", value=False)
        
        if st.button("📦 Cerrar y Archivar Período", type="primary", disabled=not confirmado, use_container_width=True):
            save_period(p)
            
            next_month = p["mes"] + 1
            next_year = p["ano"]
            if next_month > 12:
                next_month = 1
                next_year += 1
                
            p["mes"] = next_month
            p["ano"] = next_year
            p["compras"] = []
            
            st.toast(f"¡Período cerrado con éxito! Iniciando período {get_month_name(next_month)} {next_year}.", icon="📦")
            st.balloons()
            st.rerun()
