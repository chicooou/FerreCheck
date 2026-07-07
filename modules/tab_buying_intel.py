"""
Módulo UI de la pestaña "Inteligencia de Compras".
"""

import streamlit as st
import pandas as pd
import uuid
from datetime import datetime
from modules.invoice_ui import get_odoo_client
from modules.buying_intelligence import (
    run_full_analysis,
    load_analysis_cache,
    load_manual_products,
    save_manual_products,
    compute_manual_entry
)

def render_buying_intel_tab():
    st.markdown("## 🛒 Inteligencia de Compras — Productos Esenciales")
    st.markdown("Identifica los productos de mayor rotación y planifica tus compras usando datos históricos reales.")
    
    with st.expander("ℹ️ ¿Cómo funciona este semáforo?"):
        st.markdown("""
        Solo aparecen aquí los **Productos Esenciales**: aquellos que se venden con alta frecuencia constante (presentes en al menos el 75% de los meses analizados). 
        
        El semáforo se calcula comparando tu **Stock Actual** versus la **Proyección de ventas del mes** (Promedio mensual + 15% de seguridad):
        * 🔴 **Críticos (Comprar Ya):** Tienes menos del 50% del inventario necesario para cubrir este mes. Riesgo inminente de quedarte sin stock.
        * 🟡 **Alerta (Reponer Pronto):** Tienes entre el 50% y el 90% del inventario necesario. Considera agregarlos al próximo pedido.
        * 🟢 **En Orden (OK):** Tienes suficiente stock (más del 90%) para cubrir las ventas proyectadas de este mes.
        """)
    
    odoo = get_odoo_client()
    odoo_available = odoo is not None
    
    col_badge, col_ts = st.columns([1, 2])
    with col_badge:
        if odoo_available:
            st.markdown("✅ **Odoo Conectado**")
        else:
            st.markdown("🔴 **Sin conexión — Modo Manual**")
            
    # Cargar datos en session_state si no están
    if "bi_plan_data" not in st.session_state:
        plan, ts, win = load_analysis_cache()
        st.session_state.bi_plan_data = plan
        st.session_state.bi_last_run_ts = ts
        st.session_state.bi_months_window = win
        
    with col_ts:
        if st.session_state.get("bi_last_run_ts"):
            st.caption(f"Última actualización: {st.session_state.bi_last_run_ts}")

    st.write("---")
    
    # Controles superiores
    col_win, col_btn, _ = st.columns([1, 1, 2])
    with col_win:
        win_options = {
            "6 meses": 6,
            "12 meses": 12,
            "18 meses": 18,
            "24 meses": 24,
            "Todo el historial (60m)": 60
        }
        selected_win_label = st.selectbox(
            "Ventana de análisis", 
            options=list(win_options.keys()), 
            index=1, # 12 meses default
            key="bi_win_selectbox"
        )
        selected_win = win_options[selected_win_label]
        
    with col_btn:
        st.write(" ") # spacer
        if st.button("🔄 Actualizar desde Odoo", disabled=not odoo_available, use_container_width=True):
            with st.spinner("Analizando historial de ventas en Odoo..."):
                try:
                    plan = run_full_analysis(odoo, months_window=selected_win)
                    st.session_state.bi_plan_data = plan
                    st.session_state.bi_last_run_ts = datetime.utcnow().isoformat()
                    st.session_state.bi_months_window = selected_win
                    st.success("Análisis completado.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al analizar datos de Odoo: {str(e)}")

    # Preparar datos combinados
    plan_odoo = st.session_state.get("bi_plan_data", [])
    manual_prods_raw = load_manual_products()
    plan_manual = [compute_manual_entry(p) for p in manual_prods_raw]
    
    full_plan = plan_odoo + plan_manual
    # Re-ordenar la combinación por urgencia y luego por a_comprar
    full_plan.sort(key=lambda x: (x.get("urgencia", 0), x.get("a_comprar", 0)), reverse=True)

    if not full_plan:
        st.info("No hay productos esenciales detectados ni agregados manualmente. Presiona 'Actualizar desde Odoo' o agrega productos manualmente.")
    else:
        # KPIs
        criticos = sum(1 for p in full_plan if p["urgencia"] == 3)
        alerta = sum(1 for p in full_plan if p["urgencia"] == 2)
        ok = sum(1 for p in full_plan if p["urgencia"] == 1)
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("🔴 Críticos (Comprar Ya)", criticos)
        c2.metric("🟡 Alerta (Reponer Pronto)", alerta)
        c3.metric("🟢 En Orden (OK)", ok)
        c4.metric("📦 Total Esenciales", len(full_plan))
        
        st.write("---")
        
        # Filtros
        filtro = st.radio("Filtrar por estado:", ["Todos", "🔴 Críticos", "🟡 Por Reponer", "🟢 OK"], horizontal=True, key="bi_filter_radio")
        
        df = pd.DataFrame(full_plan)
        if filtro == "🔴 Críticos":
            df = df[df["urgencia"] == 3]
        elif filtro == "🟡 Por Reponer":
            df = df[df["urgencia"] == 2]
        elif filtro == "🟢 OK":
            df = df[df["urgencia"] == 1]
            
        if not df.empty:
            df_visual = df[["semaforo", "nombre", "codigo", "stock_actual", "promedio_mensual", "proyeccion_mes", "a_comprar", "cobertura_pct", "fuente"]].copy()
            df_visual = df_visual.rename(columns={
                "semaforo": "🚦",
                "nombre": "Producto",
                "codigo": "Código",
                "stock_actual": "Stock",
                "promedio_mensual": "Prom/Mes",
                "proyeccion_mes": "Proyección",
                "a_comprar": "Comprar",
                "cobertura_pct": "Cobertura %",
                "fuente": "Fuente"
            })
            
            # Formatear numéricos para display, pero usar column_config para interactividad
            max_proy = float(df_visual["Proyección"].max()) if df_visual["Proyección"].max() > 0 else 100.0
            
            st.dataframe(
                df_visual,
                column_config={
                    "Comprar": st.column_config.ProgressColumn(
                        "Comprar",
                        help="Cantidad requerida a comprar",
                        format="%.0f",
                        min_value=0,
                        max_value=max_proy,
                    ),
                    "Cobertura %": st.column_config.NumberColumn(
                        "Cobertura %",
                        format="%.1f%%"
                    ),
                    "Stock": st.column_config.NumberColumn(format="%.1f"),
                    "Prom/Mes": st.column_config.NumberColumn(format="%.1f"),
                    "Proyección": st.column_config.NumberColumn(format="%.1f"),
                },
                hide_index=True,
                use_container_width=True
            )
            st.caption("Proyección = Promedio Mensual × 1.15 (colchón de seguridad 15%)")
        else:
            st.info("No hay productos que coincidan con el filtro seleccionado.")
            
    st.write("---")
    
    # Manejo manual
    with st.expander("➕ Agregar Producto Manualmente"):
        with st.form("form_manual_product"):
            nombre = st.text_input("Nombre del Producto *", key="bi_new_nombre")
            codigo = st.text_input("Código Interno (opcional)", key="bi_new_codigo")
            stock = st.number_input("Stock Actual", min_value=0.0, step=1.0, key="bi_new_stock")
            promedio = st.number_input("Promedio Mensual Estimado (uds)", min_value=1.0, step=1.0, key="bi_new_promedio")
            submitted = st.form_submit_button("💾 Guardar Producto")
            
            if submitted:
                if not nombre.strip():
                    st.error("El nombre del producto es obligatorio.")
                else:
                    new_prod = {
                        "id": str(uuid.uuid4()),
                        "nombre": nombre.strip(),
                        "codigo": codigo.strip(),
                        "stock_actual": stock,
                        "promedio_mensual": promedio,
                        "fuente": "manual"
                    }
                    manual_prods_raw.append(new_prod)
                    save_manual_products(manual_prods_raw)
                    st.success("Producto manual agregado exitosamente.")
                    st.rerun()
                    
    with st.expander("✏️ Editar / Eliminar Producto Manual"):
        if not manual_prods_raw:
            st.info("No hay productos manuales registrados.")
        else:
            prod_options = {p["id"]: f"{p['nombre']} (Stock: {p['stock_actual']})" for p in manual_prods_raw}
            selected_id = st.selectbox("Seleccionar producto manual", options=list(prod_options.keys()), format_func=lambda x: prod_options[x], key="bi_edit_select")
            
            selected_prod = next((p for p in manual_prods_raw if p["id"] == selected_id), None)
            
            if selected_prod:
                with st.form("form_edit_manual"):
                    new_stock = st.number_input("Actualizar Stock", min_value=0.0, value=float(selected_prod["stock_actual"]), step=1.0, key="bi_edit_stock")
                    new_prom = st.number_input("Actualizar Promedio Mensual", min_value=1.0, value=float(selected_prod["promedio_mensual"]), step=1.0, key="bi_edit_prom")
                    
                    c_save, c_del = st.columns(2)
                    with c_save:
                        if st.form_submit_button("💾 Actualizar"):
                            selected_prod["stock_actual"] = new_stock
                            selected_prod["promedio_mensual"] = new_prom
                            save_manual_products(manual_prods_raw)
                            st.success("Producto actualizado.")
                            st.rerun()
                    with c_del:
                        if st.form_submit_button("❌ Eliminar", type="primary"):
                            manual_prods_raw = [p for p in manual_prods_raw if p["id"] != selected_id]
                            save_manual_products(manual_prods_raw)
                            st.success("Producto eliminado.")
                            st.rerun()
