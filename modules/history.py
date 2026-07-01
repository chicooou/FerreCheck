"""
Módulo de Gestión de Historial, Persistencia Activa (Autosave) y Copias de Seguridad para FerreCheck.
Maneja la carga/guardado automático para evitar pérdida de datos al recargar la página,
integrando de manera nativa la conexión con Google Sheets.
"""

import streamlit as st
import json
import os
import datetime
import pandas as pd
from config import format_currency, MESES, get_month_name, ESTRATEGIAS
from modules.engine import (
    calcular_gastos_totales,
    calcular_limite_compra,
    calcular_total_compras,
    calcular_utilidad_estimada,
    calcular_utilidad_por_modalidad,
    resolver_deudas_para_herencia,
    calcular_fecha_vencimiento
)
from modules.sheets import (
    is_sheets_active,
    load_all_data_from_sheets,
    sync_period_to_sheets,
    sync_all_purchases_to_sheets,
    sync_all_sales_to_sheets,
    close_period_in_sheets
)

HISTORY_FILE = os.path.join("data", "history.json")
CURRENT_PERIOD_FILE = os.path.join("data", "current_period.json")

def load_history() -> dict:
    """Carga el historial desde Google Sheets si está activo, o desde JSON local."""
    if is_sheets_active():
        # Si ya se cargó en esta ejecución, retornar caché del state
        if "historial_sheets" in st.session_state:
            return st.session_state.historial_sheets
            
        # Cargar desde Google Sheets
        _, history = load_all_data_from_sheets()
        if history is not None:
            st.session_state.historial_sheets = history
            return history
            
    # Fallback local
    if not os.path.exists(HISTORY_FILE):
        return {}
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_history(history: dict):
    """Guarda el historial en el archivo JSON local."""
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)

def load_current_period() -> dict:
    """
    Carga el estado del período actual.
    Si Google Sheets está activo, lo jala desde Sheets.
    Si no, de manera local (autosave).
    """
    if is_sheets_active():
        if "periodo_actual_sheets" in st.session_state:
            return st.session_state.periodo_actual_sheets
            
        p_sheets, h_sheets = load_all_data_from_sheets()
        if p_sheets is not None:
            # Garantizar que ventas_diarias exista
            if "ventas_diarias" not in p_sheets:
                p_sheets["ventas_diarias"] = []
            st.session_state.periodo_actual_sheets = p_sheets
            st.session_state.historial_sheets = h_sheets
            return p_sheets
            
    # Fallback local
    if os.path.exists(CURRENT_PERIOD_FILE):
        try:
            with open(CURRENT_PERIOD_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data:
                    if "ventas_diarias" not in data:
                        data["ventas_diarias"] = []
                    if "compras" not in data:
                        data["compras"] = []
                    # Nuevos campos: deudas heredadas y cola de deudas futuras
                    if "deudas_heredadas" not in data:
                        data["deudas_heredadas"] = []
                    if "deudas_futuras" not in data:
                        data["deudas_futuras"] = []
                    return data
        except Exception:
            pass

    # Valores por defecto iniciales
    now = datetime.datetime.now()
    return {
        "ano": now.year,
        "mes": now.month,
        "ventas": 100000.0,
        "gastos": {
            "planilla": 15000.0,
            "renta": 8000.0,
            "luz": 2500.0,
            "otros": 4500.0
        },
        "estrategia": "balance",
        "compras": [],
        "ventas_diarias": [],
        "deudas_heredadas": [],
        "deudas_futuras": []
    }

def save_current_period(p: dict):
    """Guarda el estado del período actual en disco de manera silenciosa."""
    os.makedirs(os.path.dirname(CURRENT_PERIOD_FILE), exist_ok=True)
    try:
        with open(CURRENT_PERIOD_FILE, "w", encoding="utf-8") as f:
            json.dump(p, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

def save_period(p: dict):
    """Guarda el período actual cerrado en el archivo de historial."""
    if is_sheets_active():
        close_period_in_sheets(p)
        # Limpiar caché de sesión de Sheets para forzar recarga de historial
        if "historial_sheets" in st.session_state:
            del st.session_state.historial_sheets
        return

    # Fallback local
    history = load_history()
    year_str = str(p["ano"])
    month_str = str(p["mes"])
    
    if year_str not in history:
        history[year_str] = {}
        
    history[year_str][month_str] = {
        "ventas": p["ventas"],
        "gastos": p["gastos"].copy(),
        "estrategia": p["estrategia"],
        "compras": p["compras"].copy(),
        "ventas_diarias": p.get("ventas_diarias", []).copy()
    }
    
    save_history(history)

def render_history_view():
    """
    Muestra el historial completo de períodos cerrados de manera organizada,
    añadiendo gráficos de tendencias con Plotly, tabla ejecutiva consolidada,
    buscador histórico de proveedores y ranking de Top 5 Proveedores.
    También integra la funcionalidad de copias de seguridad unificadas.
    """
    st.markdown("### 📜 Historial de Períodos Cerrados")
    history = load_history()
    
    # 1. Sección de Copia de Seguridad y Restauración (Backup & Restore)
    with st.expander("💾 Copia de Seguridad y Restauración (Sin Base de Datos)", expanded=False):
        if is_sheets_active():
            st.info("💡 **Google Sheets está Activo:** Tus datos se guardan y sincronizan automáticamente en la nube en tiempo real. Esta sección de respaldo local es opcional pero te sirve como copia de seguridad personal extra.")
        col_backup, col_restore = st.columns(2, gap="medium")
        
        with col_backup:
            st.markdown("**📥 Descargar Respaldo Completo**")
            st.write("Descarga una copia que incluye tu historial completo de meses anteriores y tu configuración del mes activo actual.")
            
            backup_payload = {
                "history": history,
                "current_period": st.session_state.periodo_actual
            }
            backup_data = json.dumps(backup_payload, indent=2, ensure_ascii=False)
            
            st.download_button(
                label="📥 Descargar Archivo de Respaldo (.json)",
                data=backup_data,
                file_name="FerreCheck_Respaldo_Total.json",
                mime="application/json",
                use_container_width=True
            )
                
        with col_restore:
            st.markdown("**📤 Restaurar Respaldo**")
            st.write("Sube tu archivo de respaldo (.json) para restaurar tu configuración activa e historial de compras instantáneamente.")
            uploaded_file = st.file_uploader("Subir archivo de respaldo (.json)", type=["json"], label_visibility="collapsed")
            
            if uploaded_file is not None:
                try:
                    uploaded_data = json.load(uploaded_file)
                    
                    if isinstance(uploaded_data, dict) and "history" in uploaded_data and "current_period" in uploaded_data:
                        if st.button("🔄 Confirmar y Restaurar Datos", type="primary", use_container_width=True):
                            save_history(uploaded_data["history"])
                            save_current_period(uploaded_data["current_period"])
                            st.session_state.periodo_actual = uploaded_data["current_period"]
                            
                            # Si Sheets está activo, sincronizar en la nube
                            if is_sheets_active():
                                sync_period_to_sheets(uploaded_data["current_period"], "Activo")
                                sync_all_purchases_to_sheets(uploaded_data["current_period"]["compras"], uploaded_data["current_period"])
                                # DEEP-03 FIX: Sincronizar también las ventas diarias restauradas
                                ventas_restauradas = uploaded_data["current_period"].get("ventas_diarias", [])
                                if ventas_restauradas:
                                    from modules.sheets import sync_all_sales_to_sheets
                                    sync_all_sales_to_sheets(ventas_restauradas, uploaded_data["current_period"])
                                # Guardar también el histórico completo en Google Sheets requeriría iterar,
                                # pero lo guardamos en caché temporal
                                if "historial_sheets" in st.session_state:
                                    st.session_state.historial_sheets = uploaded_data["history"]
                                    
                            st.success("✅ ¡Historial y Configuración Activa restaurados con éxito!")
                            st.rerun()
                    elif isinstance(uploaded_data, dict):
                        if st.button("🔄 Confirmar y Restaurar Historial", type="primary", use_container_width=True):
                            save_history(uploaded_data)
                            st.success("✅ Historial restaurado (configuración actual sin cambios).")
                            st.rerun()
                    else:
                        st.error("⚠️ El formato del archivo de respaldo no es válido.")
                except Exception as e:
                    st.error(f"❌ Error al leer el archivo de respaldo: {str(e)}")

    st.write("---")

    if not history:
        st.info("📂 No hay períodos archivados en el historial todavía. Cierra un período mensual en la barra lateral para registrarlo aquí.")
        return

    # --- PROCESAMIENTO DE DATOS HISTÓRICOS PARA ANALÍTICAS ---
    registros = []
    todas_las_compras = []
    todas_las_ventas_diarias = []
    
    for yr in sorted(history.keys(), key=int):
        for m_key in sorted(history[yr].keys(), key=int):
            m_data = history[yr][m_key]
            m_num = int(m_key)
            
            # Cálculos financieros por período cerrado
            g_totales = calcular_gastos_totales(m_data["gastos"])
            total_c = calcular_total_compras(m_data["compras"])
            res_lim = calcular_limite_compra(m_data["ventas"], g_totales, m_data["estrategia"])
            utilidad = calcular_utilidad_estimada(m_data["ventas"], g_totales, total_c)
            
            periodo_label = f"{get_month_name(m_num)} {yr}"
            
            registros.append({
                "Año": int(yr),
                "Mes Num": m_num,
                "Período": periodo_label,
                "Ventas": m_data["ventas"],
                "Gastos Fijos": g_totales,
                "Límite de Compra": res_lim["limite_real"],
                "Compras Realizadas": total_c,
                "Utilidad Operativa": utilidad,
                "% Consumo": (total_c / res_lim["limite_real"] * 100.0) if res_lim["limite_real"] > 0 else 0.0,
                "Estrategia": ESTRATEGIAS.get(m_data["estrategia"], ESTRATEGIAS["balance"])["nombre"],
                "estrategia_raw": m_data["estrategia"]
            })
            
            # Guardar transacciones individuales de compras para el buscador de proveedores
            for c in m_data.get("compras", []):
                todas_las_compras.append({
                    "Período": periodo_label,
                    "Fecha": c.get("fecha", ""),
                    "Proveedor": c.get("proveedor", "Desconocido"),
                    "Monto": c.get("monto", 0.0),
                    "Modalidad": c.get("modalidad", "Contado"),
                    "Descripción": c.get("nota", "")
                })
                
            # Guardar ventas diarias para exportador Excel
            for v in m_data.get("ventas_diarias", []):
                todas_las_ventas_diarias.append({
                    "Período": periodo_label,
                    "Fecha": v.get("fecha", ""),
                    "Monto": v.get("monto", 0.0)
                })
                
    df_periodos = pd.DataFrame(registros)
    df_compras_todas = pd.DataFrame(todas_las_compras)
    df_ventas_todas = pd.DataFrame(todas_las_ventas_diarias)

    # 1.1 Botón de Exportación Avanzada a Excel Multi-Hoja (TIER 3 - FEATURE 9)
    import io
    excel_buffer = io.BytesIO()
    try:
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            # Hoja 1: Resumen Ejecutivo
            if not df_periodos.empty:
                df_exec = df_periodos[["Período", "Ventas", "Gastos Fijos", "Límite de Compra", "Compras Realizadas", "Utilidad Operativa", "Estrategia"]].copy()
                df_exec.to_excel(writer, sheet_name="Resumen Ejecutivo", index=False)
            
            # Hoja 2: Detalle de Compras
            if not df_compras_todas.empty:
                df_compras_todas.to_excel(writer, sheet_name="Historial de Compras", index=False)
            else:
                pd.DataFrame(columns=["Mensaje"]).to_excel(writer, sheet_name="Historial de Compras", index=False)
                
            # Hoja 3: Ventas Diarias
            if not df_ventas_todas.empty:
                df_ventas_todas.to_excel(writer, sheet_name="Ventas Diarias", index=False)
            else:
                pd.DataFrame(columns=["Mensaje"]).to_excel(writer, sheet_name="Ventas Diarias", index=False)
                
        st.download_button(
            label="📊 Exportar Datos a Excel Completo (.xlsx)",
            data=excel_buffer.getvalue(),
            file_name="FerreCheck_Reporte_Multiperiodo.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
    except Exception as e:
        st.error(f"Error al generar reporte Excel: {str(e)}")

    # --- ANÁLISIS DE ANOMALÍAS E ALERTAS FINANCIERAS (TIER 3 - FEATURE 10) ---
    st.markdown("#### 🚨 Alertas y Anomalías Financieras Detectadas")
    alertas = []
    
    if len(df_periodos) >= 2:
        # Analizar tendencia de Gastos Fijos
        gastos_ultimos = df_periodos["Gastos Fijos"].iloc[-2:].tolist()
        dif_gastos = gastos_ultimos[1] - gastos_ultimos[0]
        if dif_gastos > 0:
            pct_g = (dif_gastos / gastos_ultimos[0]) * 100.0
            if pct_g >= 10.0:
                alertas.append(f"⚠️ **Incremento de Costos:** Los Gastos Fijos aumentaron un **{pct_g:.1f}%** ({format_currency(dif_gastos)}) en el último mes. Evalúa optimizar planilla o servicios.")
                
        # Analizar tendencia de Ventas
        ventas_ultimas = df_periodos["Ventas"].iloc[-2:].tolist()
        dif_ventas = ventas_ultimas[1] - ventas_ultimas[0]
        if dif_ventas < 0:
            pct_v = (abs(dif_ventas) / ventas_ultimas[0]) * 100.0
            if pct_v >= 15.0:
                alertas.append(f"🚨 **Caída de Facturación:** Las ventas bajaron un **{pct_v:.1f}%** ({format_currency(abs(dif_ventas))}) este último período. Revisa la afluencia de clientes.")
                
    # Rendimiento de Estrategias
    if not df_periodos.empty:
        est_perf = df_periodos.groupby("Estrategia")["Utilidad Operativa"].mean().reset_index()
        if not est_perf.empty:
            mejor_estr = est_perf.sort_values(by="Utilidad Operativa", ascending=False).iloc[0]
            alertas.append(f"💡 **Estrategia Óptima:** Históricamente, la estrategia **'{mejor_estr['Estrategia']}'** ha generado el mayor promedio de utilidad mensual (**{format_currency(mejor_estr['Utilidad Operativa'])}**).")

    # Proveedores inactivos (anomalía de abandono de proveedor)
    if len(df_periodos) >= 3 and not df_compras_todas.empty:
        # Lista de proveedores comprados en periodos anteriores
        prov_historicos = set(df_compras_todas["Proveedor"].unique())
        # Proveedores comprados en el último mes
        ultimo_periodo = df_periodos["Período"].iloc[-1]
        prov_recientes = set(df_compras_todas[df_compras_todas["Período"] == ultimo_periodo]["Proveedor"].unique())
        
        prov_inactivos = prov_historicos - prov_recientes
        if prov_inactivos:
            lista_inactivos = ", ".join(list(prov_inactivos)[:3])
            alertas.append(f"📦 **Proveedores Inactivos:** Este último mes no se registraron compras con proveedores frecuentes de meses anteriores como: *{lista_inactivos}*.")

    if alertas:
        for alerta in alertas:
            st.markdown(
                f"""
                <div style="background-color: rgba(255, 152, 0, 0.08); border-left: 4px solid #FF9800; padding: 10px; border-radius: 4px; margin-bottom: 8px; font-size: 13px;">
                    {alerta}
                </div>
                """,
                unsafe_allow_html=True
            )
    else:
        st.success("✅ No se detectaron anomalías o fluctuaciones de riesgo en el historial financiero.")
        
    st.write(" ")

    # --- KPIs DE RENDIMIENTO HISTÓRICO GLOBAL (TIER 2 - FEATURE 5) ---
    st.markdown("#### 🎯 KPIs de Rendimiento Histórico")
    kpi_col1, kpi_col2, kpi_col3, kpi_col4 = st.columns(4)
    
    total_ventas_h = df_periodos["Ventas"].sum()
    total_utilidad_h = df_periodos["Utilidad Operativa"].sum()
    promedio_ventas_h = df_periodos["Ventas"].mean()
    
    # Identificar mejor y peor mes por utilidad
    mejor_mes_row = df_periodos.loc[df_periodos["Utilidad Operativa"].idxmax()]
    peor_mes_row = df_periodos.loc[df_periodos["Utilidad Operativa"].idxmin()]
    
    with kpi_col1:
        st.markdown(
            f"""
            <div style="background-color: rgba(0, 192, 242, 0.1); border-left: 4px solid #00C0F2; padding: 12px; border-radius: 4px;">
                <span style="font-size: 11px; color: #8C9CAE; font-weight: 600; text-transform: uppercase;">Ventas Totales Históricas</span>
                <h4 style="margin: 4px 0 0 0; color: var(--text-color, #FFFFFF); font-size: 20px; font-weight: 700;">{format_currency(total_ventas_h)}</h4>
            </div>
            """,
            unsafe_allow_html=True
        )
    with kpi_col2:
        st.markdown(
            f"""
            <div style="background-color: rgba(9, 171, 59, 0.1); border-left: 4px solid #09AB3B; padding: 12px; border-radius: 4px;">
                <span style="font-size: 11px; color: #8C9CAE; font-weight: 600; text-transform: uppercase;">Utilidad Total Histórica</span>
                <h4 style="margin: 4px 0 0 0; color: var(--text-color, #FFFFFF); font-size: 20px; font-weight: 700;">{format_currency(total_utilidad_h)}</h4>
            </div>
            """,
            unsafe_allow_html=True
        )
    with kpi_col3:
        st.markdown(
            f"""
            <div style="background-color: rgba(255, 152, 0, 0.1); border-left: 4px solid #FF9800; padding: 12px; border-radius: 4px;">
                <span style="font-size: 11px; color: #8C9CAE; font-weight: 600; text-transform: uppercase;">Promedio de Ventas</span>
                <h4 style="margin: 4px 0 0 0; color: var(--text-color, #FFFFFF); font-size: 20px; font-weight: 700;">{format_currency(promedio_ventas_h)}</h4>
            </div>
            """,
            unsafe_allow_html=True
        )
    with kpi_col4:
        st.markdown(
            f"""
            <div style="background-color: rgba(255, 75, 75, 0.1); border-left: 4px solid #FF4B4B; padding: 12px; border-radius: 4px;">
                <span style="font-size: 11px; color: #8C9CAE; font-weight: 600; text-transform: uppercase;">Mejor Mes (Utilidad)</span>
                <h4 style="margin: 4px 0 0 0; color: var(--text-color, #FFFFFF); font-size: 15px; font-weight: 700;">{mejor_mes_row["Período"]}</h4>
                <span style="font-size: 12px; color: #09AB3B; font-weight: 600;">{format_currency(mejor_mes_row["Utilidad Operativa"])}</span>
            </div>
            """,
            unsafe_allow_html=True
        )
        
    st.write(" ")

    # --- COMPARADOR DE DOS PERÍODOS (TIER 2 - FEATURE 6) ---
    with st.expander("📅 Comparador Lado a Lado de Dos Períodos", expanded=False):
        st.markdown("**Elige dos meses de tu historial para comparar sus KPIs clave directamente**")
        comp_col1, comp_col2 = st.columns(2)
        
        lista_periodos = df_periodos["Período"].tolist()
        
        with comp_col1:
            periodo_a = st.selectbox("Selecciona Período A (Base):", lista_periodos, index=max(0, len(lista_periodos)-2))
        with comp_col2:
            periodo_b = st.selectbox("Selecciona Período B (Comparativo):", lista_periodos, index=max(0, len(lista_periodos)-1))
            
        if periodo_a and periodo_b:
            row_a = df_periodos[df_periodos["Período"] == periodo_a].iloc[0]
            row_b = df_periodos[df_periodos["Período"] == periodo_b].iloc[0]
            
            def get_delta_str(val_a, val_b, is_currency=True):
                diff = val_b - val_a
                pct = (diff / val_a * 100.0) if val_a > 0 else 0.0
                signo = "+" if diff >= 0 else ""
                color = "#09AB3B" if diff >= 0 else "#FF4B4B"
                
                # Para gastos, un incremento se pinta de rojo y decremento de verde
                # (excepto si son ventas/utilidad)
                return diff, pct, signo, color
                
            metrics_comp = []
            for label, key, invert_color in [
                ("Ventas", "Ventas", False),
                ("Gastos Fijos", "Gastos Fijos", True),
                ("Límite de Compra", "Límite de Compra", False),
                ("Compras Realizadas", "Compras Realizadas", True),
                ("Utilidad Operativa", "Utilidad Operativa", False)
            ]:
                val_a = row_a[key]
                val_b = row_b[key]
                diff, pct, signo, color = get_delta_str(val_a, val_b)
                if invert_color:
                    color = "#FF4B4B" if diff > 0 else "#09AB3B" if diff < 0 else "#8C9CAE"
                
                metrics_comp.append({
                    "Métrica": label,
                    periodo_a: format_currency(val_a),
                    periodo_b: format_currency(val_b),
                    "Diferencia (Q)": f"{signo}{format_currency(diff)}",
                    "Diferencia (%)": f"<span style='color: {color}; font-weight: bold;'>{signo}{pct:.1f}%</span>"
                })
                
            df_comp_table = pd.DataFrame(metrics_comp)
            st.write(" ")
            st.markdown(df_comp_table.to_html(escape=False, index=False), unsafe_allow_html=True)
            st.write(" ")

    # 2. SECCIÓN DE ANALÍTICAS E INTERACTIVIDAD (PLOTLY)
    st.markdown("#### 📊 Panel de Análisis de Tendencias y Estacionalidad")
    import plotly.graph_objects as go
    
    col_chart_1, col_chart_2 = st.columns(2)
    
    with col_chart_1:
        # Gráfico 1: Ventas, Compras y Utilidad en el tiempo
        fig1 = go.Figure()
        fig1.add_trace(go.Scatter(x=df_periodos["Período"], y=df_periodos["Ventas"], name="Ventas", line=dict(color="#00C0F2", width=3), mode='lines+markers'))
        fig1.add_trace(go.Scatter(x=df_periodos["Período"], y=df_periodos["Compras Realizadas"], name="Compras", line=dict(color="#FF9800", width=3), mode='lines+markers'))
        fig1.add_trace(go.Scatter(x=df_periodos["Período"], y=df_periodos["Utilidad Operativa"], name="Utilidad", line=dict(color="#09AB3B", width=3), mode='lines+markers'))
        fig1.update_layout(
            title="Evolución de Flujo Financiero",
            xaxis_title="Período",
            yaxis_title="Monto (Q)",
            hovermode="x unified",
            template="plotly_dark",
            margin=dict(l=20, r=20, t=40, b=20),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)"
        )
        st.plotly_chart(fig1, use_container_width=True)

    with col_chart_2:
        # Gráfico 2: Estacionalidad de Ventas por Mes Calendario (TIER 2 - FEATURE 8)
        # Agrupamos todas las ventas por el número del mes calendario y promediamos
        df_estacional = df_periodos.groupby("Mes Num")["Ventas"].mean().reset_index()
        # Mapeamos a los nombres de los meses
        df_estacional["Nombre Mes"] = df_estacional["Mes Num"].apply(get_month_name)
        df_estacional = df_estacional.sort_values(by="Mes Num")
        
        fig2 = go.Figure()
        fig2.add_trace(go.Bar(
            x=df_estacional["Nombre Mes"],
            y=df_estacional["Ventas"],
            marker_color="#00C0F2",
            hovertemplate="Mes: %{x}<br>Ventas Promedio: Q %{y:,.2f}<extra></extra>"
        ))
        fig2.update_layout(
            title="Temporalidad: Promedio de Ventas por Mes",
            xaxis_title="Mes Calendario",
            yaxis_title="Ventas Promedio (Q)",
            hovermode="x unified",
            template="plotly_dark",
            margin=dict(l=20, r=20, t=40, b=20),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)"
        )
        st.plotly_chart(fig2, use_container_width=True)


    # 3. TABLA RESUMEN EJECUTIVA
    with st.expander("🏆 Ver Tabla Resumen Ejecutiva", expanded=True):
        st.markdown("**Resumen Consolidado de Todos los Períodos**")
        df_visual = df_periodos.copy()
        
        # Formatear columnas para la visualización premium
        df_visual["Ventas"] = df_visual["Ventas"].apply(format_currency)
        df_visual["Gastos Fijos"] = df_visual["Gastos Fijos"].apply(format_currency)
        df_visual["Límite de Compra"] = df_visual["Límite de Compra"].apply(format_currency)
        df_visual["Compras Realizadas"] = df_visual["Compras Realizadas"].apply(format_currency)
        df_visual["Utilidad Operativa"] = df_visual["Utilidad Operativa"].apply(format_currency)
        df_visual["% Consumo"] = df_visual["% Consumo"].apply(lambda x: f"{x:.1f}%")
        
        # Mostrar tabla interactiva sin las columnas de ordenación interna
        df_visual_show = df_visual[["Período", "Ventas", "Gastos Fijos", "Límite de Compra", "Compras Realizadas", "% Consumo", "Utilidad Operativa", "Estrategia"]]
        st.dataframe(df_visual_show, use_container_width=True, hide_index=True)

    # 4. BUSCADOR DE PROVEEDORES HISTÓRICOS Y TOP 5
    col_busq, col_top = st.columns([11, 9], gap="large")
    
    with col_busq:
        st.markdown("#### 🔍 Buscador de Compras por Proveedor")
        busqueda = st.text_input("Ingresa el nombre del proveedor para buscar:", placeholder="Ferretería, Cemento, etc...")
        
        if busqueda.strip() and not df_compras_todas.empty:
            df_filtrado = df_compras_todas[df_compras_todas["Proveedor"].str.contains(busqueda, case=False, na=False)]
            if not df_filtrado.empty:
                st.success(f"Se encontraron {len(df_filtrado)} compras asociadas a '{busqueda}':")
                df_filtrado_show = df_filtrado.copy()
                df_filtrado_show["Monto"] = df_filtrado_show["Monto"].apply(format_currency)
                st.dataframe(df_filtrado_show, use_container_width=True, hide_index=True)
                
                total_filtrado = df_filtrado["Monto"].sum()
                st.info(f"💰 **Total invertido en este proveedor:** {format_currency(total_filtrado)}")
            else:
                st.warning(f"No se encontraron compras para el proveedor '{busqueda}'.")
        else:
            st.caption("Escribe arriba para buscar transacciones históricas en todos los meses.")

    with col_top:
        st.markdown("#### 📦 Ranking de Proveedores Clave (Top 5 Histórico)")
        if not df_compras_todas.empty:
            top_prov = df_compras_todas.groupby("Proveedor")["Monto"].sum().reset_index()
            top_prov = top_prov.sort_values(by="Monto", ascending=False).head(5)
            
            monto_max = top_prov["Monto"].max() if not top_prov.empty else 1.0
            
            for idx, row in top_prov.iterrows():
                prov_name = row["Proveedor"]
                prov_monto = row["Monto"]
                pct_barra = (prov_monto / monto_max) * 100.0 if monto_max > 0 else 0
                
                st.markdown(
                    f"""
                    <div style="margin-bottom: 10px;">
                        <div style="display:flex; justify-content:space-between; align-items:center; font-size:13px; margin-bottom:2px;">
                            <span style="font-weight:600; color:var(--text-color, #FFFFFF);">{prov_name}</span>
                            <span style="font-weight:bold; color:#09AB3B;">{format_currency(prov_monto)}</span>
                        </div>
                        <div style="background-color: rgba(128,128,128,0.15); border-radius: 4px; height: 6px; width: 100%; overflow: hidden;">
                            <div style="background-color: #00C0F2; width: {pct_barra}%; height: 100%; border-radius: 4px;"></div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
        else:
            st.info("No hay suficientes datos de compras para armar el ranking.")

    st.write("---")

    # 5. Visualización de Períodos Históricos Detallados (Tabs por Año)
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
                        df_hist["Modalidad"] = df_hist.get("modalidad", "Contado")
                        df_hist = df_hist.rename(columns={"proveedor": "Proveedor", "nota": "Descripción"})
                        df_hist_visual = df_hist[["Fecha", "Proveedor", "Monto", "Modalidad", "Descripción"]]
                        df_hist_visual.index = range(1, len(df_hist_visual) + 1)
                        st.dataframe(df_hist_visual, use_container_width=True)

def render_close_period_button(p: dict):
    """Renderiza la sección de cierre de período en el sidebar, incluyendo
    el panel de resolución de deudas a crédito con soporte para 'Proveedor Desaparecido'."""
    st.sidebar.markdown("---")
    st.sidebar.subheader("📦 Cierre de Período")

    # Importación tardía intencional para evitar circularidad
    from modules.daily_sales import get_monthly_sales_total
    total_diarias = get_monthly_sales_total(p)

    next_month = p["mes"] + 1
    next_year = p["ano"]
    if next_month > 12:
        next_month = 1
        next_year += 1

    with st.sidebar.expander("🔐 Cerrar Mes Actual", expanded=False):
        if total_diarias > 0:
            st.markdown(
                f"""
                <div style="background-color: rgba(9, 171, 59, 0.1); padding: 10px; border-radius: 5px; border-left: 3px solid #09AB3B; margin-bottom: 10px;">
                    💡 Tienes <b>{format_currency(total_diarias)}</b> acumulados en Caja Diaria.<br><br>
                    Al cerrar, este monto se guardará como el total real facturado de este mes y se pre-llenará
                    automáticamente como 'Ventas Mes Anterior' para {get_month_name(next_month)}.
                </div>
                """,
                unsafe_allow_html=True
            )
        else:
            st.write("El cierre archivará las ventas, gastos y compras registradas para este período en el historial multi-período.")

        # ─── Panel de Resolución de Deudas a Crédito ───────────────────────────
        # Calcular qué créditos heredarán al siguiente período
        herencia = resolver_deudas_para_herencia(p["compras"], p["mes"], p["ano"])
        deudas_al_mes_sig = herencia["deudas_heredadas"]   # Vencen en Mes+1
        deudas_a_futuro   = herencia["deudas_futuras"]      # Vencen en Mes+2+

        # Además, las deudas_futuras del período actual que ahora vencen en Mes+1
        # (se activan desde la cola de deudas_futuras del período actual)
        deudas_futuras_activadas = [
            d for d in p.get("deudas_futuras", [])
            if d.get("mes_vencimiento") == next_month and d.get("ano_vencimiento") == next_year
        ]
        deudas_futuras_siguientes = [
            d for d in p.get("deudas_futuras", [])
            if not (d.get("mes_vencimiento") == next_month and d.get("ano_vencimiento") == next_year)
        ]

        # Todas las deudas que vencen en el mes siguiente
        todas_deudas_mes_sig = deudas_al_mes_sig + deudas_futuras_activadas

        ids_postergadas = set()

        if todas_deudas_mes_sig:
            st.markdown("---")
            st.markdown(
                f"**📋 Compromisos que vencen en {get_month_name(next_month)} {next_year}:**"
            )
            st.caption(
                "Todas están marcadas para heredarse como deudas activas del próximo mes. "
                "Si un proveedor no se presentó a cobrar, **desmárcalo** para postergarlo un mes más."
            )

            for deuda in todas_deudas_mes_sig:
                deuda_id = deuda.get("id", deuda.get("proveedor", ""))
                veces = deuda.get("veces_postergada", 0)
                label_post = f" (postergada {veces}x)" if veces > 0 else ""
                pagar = st.checkbox(
                    f"{deuda['proveedor']} — {format_currency(deuda['monto'])} "
                    f"({deuda.get('modalidad_original', deuda.get('modalidad', '?'))}){label_post}",
                    value=True,
                    key=f"pagar_{deuda_id}"
                )
                if not pagar:
                    ids_postergadas.add(deuda_id)

            if ids_postergadas:
                st.warning(
                    f"⚠️ {len(ids_postergadas)} deuda(s) marcadas como 'Proveedor Desaparecido' "
                    f"se postergarán a {get_month_name(next_month + 1 if next_month < 12 else 1)}."
                )

        if deudas_a_futuro or deudas_futuras_siguientes:
            total_cola = sum(d["monto"] for d in deudas_a_futuro) + \
                         sum(d["monto"] for d in deudas_futuras_siguientes)
            st.info(
                f"📅 {format_currency(total_cola)} en créditos vencen en Mes+2 o después "
                f"y se transferirán automáticamente a la cola de deudas futuras de {get_month_name(next_month)}."
            )
        # ───────────────────────────────────────────────────────────────────────

        st.markdown("---")
        st.warning("⚠️ Esta acción no se puede deshacer.")
        confirmado = st.checkbox("Confirmar cierre de período", value=False)

        if st.button("📦 Cerrar y Archivar Período", type="primary", disabled=not confirmado, use_container_width=True):
            # Asignar ventas reales si hay caja diaria registrada
            if total_diarias > 0:
                p["ventas"] = total_diarias

            # Guardar el período cerrado en el historial
            save_period(p)

            # ── Construir las deudas del nuevo período ──────────────────────
            nuevas_deudas_heredadas = []
            nuevas_deudas_futuras   = list(deudas_a_futuro) + list(deudas_futuras_siguientes)

            for deuda in todas_deudas_mes_sig:
                deuda_id = deuda.get("id", deuda.get("proveedor", ""))
                if deuda_id in ids_postergadas:
                    # Proveedor desaparecido: postergar un mes más
                    deuda_postergada = deuda.copy()
                    deuda_postergada["postergada"] = True
                    deuda_postergada["veces_postergada"] = deuda.get("veces_postergada", 0) + 1
                    # Recalcular el mes de vencimiento sumando 1 mes
                    mes_nuevo = next_month + 1
                    ano_nuevo = next_year
                    if mes_nuevo > 12:
                        mes_nuevo = 1
                        ano_nuevo += 1
                    deuda_postergada["mes_vencimiento"] = mes_nuevo
                    deuda_postergada["ano_vencimiento"] = ano_nuevo
                    # Si el nuevo vencimiento es el siguiente del próximo (Mes+2), va a la cola
                    nuevas_deudas_futuras.append(deuda_postergada)
                else:
                    # Se hereda normalmente como deuda activa del mes siguiente
                    nuevas_deudas_heredadas.append(deuda)
            # ──────────────────────────────────────────────────────────────────

            # Preparar el nuevo período limpio
            p["mes"] = next_month
            p["ano"] = next_year
            p["compras"] = []
            p["ventas_diarias"] = []
            p["deudas_heredadas"] = nuevas_deudas_heredadas
            p["deudas_futuras"]   = nuevas_deudas_futuras
            # NOTA: p["ventas"] NO se toca — hereda correctamente del mes cerrado.

            save_current_period(p)

            if is_sheets_active():
                if "periodo_actual_sheets" in st.session_state:
                    del st.session_state.periodo_actual_sheets
                if "historial_sheets" in st.session_state:
                    del st.session_state.historial_sheets
                try:
                    sync_period_to_sheets(p, "Activo")
                    sync_all_purchases_to_sheets([], p, "Activo")
                    sync_all_sales_to_sheets([], p, "Activo")
                except Exception as e:
                    st.sidebar.warning(f"⚠️ Período cerrado localmente, pero hubo un error al sincronizar con Google Sheets: {str(e)}")

            st.toast(f"¡Período cerrado con éxito! Iniciando período {get_month_name(next_month)} {next_year}.", icon="📦")
            st.balloons()
            st.rerun()
