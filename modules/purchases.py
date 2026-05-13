"""
Módulo de Gestión de Compras para FerreCheck.
Maneja el registro, validación, tabla visual, eliminación y sincronización en la nube (Google Sheets).
"""

import streamlit as st
import pandas as pd
import uuid
import datetime
import calendar
from config import format_currency
from modules.sheets import is_sheets_active, sync_all_purchases_to_sheets

def get_last_day_of_month(year: int, month: int) -> int:
    """Retorna el último día del mes dado."""
    return calendar.monthrange(year, month)[1]

def render_purchase_form(p: dict, limite_real: float):
    """
    Renderiza el formulario para registrar una nueva compra.
    """
    st.markdown("### 📝 Registrar Nueva Compra")
    
    if limite_real <= 0:
        st.error("🛑 No se pueden registrar compras: el límite de compra para este período es 0 due a restricciones de liquidez.")
        return

    primer_dia = datetime.date(p["ano"], p["mes"], 1)
    ultimo_dia = datetime.date(p["ano"], p["mes"], get_last_day_of_month(p["ano"], p["mes"]))
    
    hoy = datetime.date.today()
    fecha_defecto = hoy if primer_dia <= hoy <= ultimo_dia else primer_dia

    with st.form("form_nueva_compra", clear_on_submit=True):
        col_monto, col_prov = st.columns([1, 2])
        with col_monto:
            monto = st.number_input("Monto de la Compra", min_value=0.0, step=100.0, format="%f")
        with col_prov:
            proveedor = st.text_input("Nombre del Proveedor", placeholder="Ej. Aceros de Guatemala")
            
        col_fecha, col_nota = st.columns([1, 2])
        with col_fecha:
            fecha_seleccionada = st.date_input(
                "Fecha de la Compra", 
                value=fecha_defecto,
                min_value=primer_dia,
                max_value=ultimo_dia
            )
        with col_nota:
            nota = st.text_input("Nota / Detalle (Opcional)", placeholder="Ej. Lote de clavos y tornillos de 2 pulgadas")
            
        submitted = st.form_submit_button("💾 Guardar Compra", use_container_width=True)
        
        if submitted:
            if monto <= 0:
                st.error("⚠️ El monto de la compra debe ser mayor a cero.")
                return
            if not proveedor.strip():
                st.error("⚠️ Debe ingresar un proveedor válido.")
                return
            
            total_actual = sum(c["monto"] for c in p["compras"])
            nuevo_total = total_actual + monto
            excede_limite = nuevo_total > limite_real
            
            nueva_compra = {
                "id": str(uuid.uuid4()),
                "monto": monto,
                "proveedor": proveedor.strip(),
                "fecha": fecha_seleccionada.strftime("%Y-%m-%d"),
                "nota": nota.strip() if nota else "Sin descripción"
            }
            
            p["compras"].append(nueva_compra)
            
            # Sincronización en la nube si Google Sheets está activo
            if is_sheets_active():
                with st.spinner("Sincronizando con Google Sheets..."):
                    sync_all_purchases_to_sheets(p["compras"], p)
            
            if excede_limite:
                st.warning(
                    f"⚠️ Compra registrada con éxito en {'la Nube' if is_sheets_active() else 'Local'}, pero **excede el límite establecido** por "
                    f"{format_currency(nuevo_total - limite_real)}."
                )
            else:
                st.success(f"✅ Compra registrada correctamente: {nueva_compra['proveedor']} — {format_currency(nueva_compra['monto'])}")
                
            st.rerun()

def render_purchase_table(p: dict, limite_real: float):
    """
    Muestra la tabla del historial de compras registradas en el mes actual.
    """
    st.markdown("### 📋 Compras Registradas en este Período")
    
    if not p["compras"]:
        st.info("💡 No hay compras registradas para este período aún. Utiliza el formulario superior para agregar registros.")
        return

    df = pd.DataFrame(p["compras"])
    df["Monto"] = df["monto"].apply(format_currency)
    df["Fecha"] = pd.to_datetime(df["fecha"]).dt.strftime("%d/%m/%Y")
    df = df.rename(columns={"proveedor": "Proveedor", "nota": "Descripción / Nota"})
    
    df_visual = df[["Fecha", "Proveedor", "Monto", "Descripción / Nota"]]
    df_visual.index = range(1, len(df_visual) + 1)
    
    st.dataframe(df_visual, use_container_width=True)
    
    total_compras = sum(c["monto"] for c in p["compras"])
    st.markdown(
        f"**Resumen Período:** `{len(p['compras'])}` compras registradas | "
        f"**Total Acumulado:** `{format_currency(total_compras)}`"
    )

    with st.expander("🗑️ Eliminar Compra Registrada", expanded=False):
        compra_options = {
            c["id"]: f"#{i+1} - {c['fecha']} | {c['proveedor']} | {format_currency(c['monto'])}" 
            for i, c in enumerate(p["compras"])
        }
        
        compra_id_to_delete = st.selectbox(
            "Seleccione la compra a eliminar:", 
            options=list(compra_options.keys()), 
            format_func=lambda x: compra_options[x]
        )
        
        if st.button("❌ Eliminar Compra", type="primary", use_container_width=True):
            p["compras"] = [c for c in p["compras"] if c["id"] != compra_id_to_delete]
            
            # Sincronización en la nube si Google Sheets está activo
            if is_sheets_active():
                with st.spinner("Sincronizando eliminación con Google Sheets..."):
                    sync_all_purchases_to_sheets(p["compras"], p)
                    
            st.success("Compra eliminada correctamente.")
            st.rerun()
