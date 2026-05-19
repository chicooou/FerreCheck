"""
Módulo de Gestión de Ventas Diarias para FerreCheck.
Maneja el registro, validación, tabla visual, eliminación y sincronización de ventas diarias en la nube y local.
"""

import streamlit as st
import pandas as pd
import uuid
import datetime
import calendar
from config import format_currency, get_month_name
from modules.sheets import is_sheets_active, sync_all_sales_to_sheets
from modules.history import save_current_period

def get_last_day_of_month(year: int, month: int) -> int:
    """Retorna el último día del mes dado."""
    return calendar.monthrange(year, month)[1]

def get_monthly_sales_total(p: dict) -> float:
    """Calcula el total acumulado de ventas diarias del período actual."""
    return sum(v["monto"] for v in p.get("ventas_diarias", []))

def render_sales_kpis(p: dict):
    """
    Renderiza tarjetas KPI para comparar el total de ventas diarias acumuladas
    con el valor base registrado del mes anterior.
    """
    total_diario = get_monthly_sales_total(p)
    ventas_base = p.get("ventas", 0.0)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown(
            f"""
            <div style="background-color: rgba(9, 171, 59, 0.1); border-left: 5px solid #09AB3B; padding: 15px; border-radius: 5px;">
                <span style="font-size: 14px; color: #8C9CAE; font-weight: 600; text-transform: uppercase;">
                    📈 Ventas Diarias Acumuladas ({get_month_name(p['mes'])})
                </span>
                <h2 style="margin: 5px 0 0 0; color: #FFFFFF; font-size: 28px; font-weight: 700;">
                    {format_currency(total_diario)}
                </h2>
                <p style="margin: 5px 0 0 0; font-size: 12px; color: #8C9CAE;">
                    Suma total de los registros diarios ingresados este mes.
                </p>
            </div>
            """,
            unsafe_allow_html=True
        )
        
    with col2:
        st.markdown(
            f"""
            <div style="background-color: rgba(0, 192, 242, 0.1); border-left: 5px solid #00C0F2; padding: 15px; border-radius: 5px;">
                <span style="font-size: 14px; color: #8C9CAE; font-weight: 600; text-transform: uppercase;">
                    📅 Ventas del Mes Anterior (Base de Límites)
                </span>
                <h2 style="margin: 5px 0 0 0; color: #FFFFFF; font-size: 28px; font-weight: 700;">
                    {format_currency(ventas_base)}
                </h2>
                <p style="margin: 5px 0 0 0; font-size: 12px; color: #8C9CAE;">
                    Dato usado actualmente por el motor financiero para el Semáforo de Compras.
                </p>
            </div>
            """,
            unsafe_allow_html=True
        )
    st.write(" ")

def render_daily_sale_form(p: dict):
    """
    Renderiza el formulario para registrar una nueva venta diaria.
    """
    st.markdown("### 📝 Registrar Nueva Venta")
    
    primer_dia = datetime.date(p["ano"], p["mes"], 1)
    ultimo_dia = datetime.date(p["ano"], p["mes"], get_last_day_of_month(p["ano"], p["mes"]))
    
    hoy = datetime.date.today()
    fecha_defecto = hoy if primer_dia <= hoy <= ultimo_dia else primer_dia

    with st.form("form_nueva_venta", clear_on_submit=True):
        col_monto, col_fecha = st.columns([1, 1])
        with col_monto:
            monto = st.number_input("Monto de la Venta (Q)", min_value=0.0, step=100.0, format="%f")
        with col_fecha:
            fecha_seleccionada = st.date_input(
                "Fecha de la Venta", 
                value=fecha_defecto,
                min_value=primer_dia,
                max_value=ultimo_dia
            )
            
        nota = st.text_input("Nota / Descripción (Opcional)", placeholder="Ej. Venta mostrador, Pedido constructor X")
        
        import html
        nota_sanitizada = html.escape(nota.strip()) if nota else "Sin descripción"
        nota_sanitizada = nota_sanitizada.replace('"', '&quot;').replace("'", '&#x27;')
            
        submitted = st.form_submit_button("💾 Guardar Venta Diaria", use_container_width=True)
        
        if submitted:
            if monto <= 0:
                st.error("⚠️ El monto de la venta debe ser mayor a cero.")
                return
                
            nueva_venta = {
                "id": str(uuid.uuid4()),
                "monto": monto,
                "fecha": fecha_seleccionada.strftime("%Y-%m-%d"),
                "nota": nota_sanitizada
            }
            
            if "ventas_diarias" not in p:
                p["ventas_diarias"] = []
                
            p["ventas_diarias"].append(nueva_venta)
            
            # Guardado silencioso local
            save_current_period(p)
            
            # Sincronización con la nube
            if is_sheets_active():
                with st.spinner("Sincronizando con Google Sheets..."):
                    sync_all_sales_to_sheets(p["ventas_diarias"], p)
            
            st.success(f"✅ Venta registrada correctamente: {format_currency(monto)} en fecha {nueva_venta['fecha']}")
            st.rerun()
 
def render_daily_sales_table(p: dict):
    """
    Muestra la tabla de las ventas diarias registradas y la sección para eliminar registros.
    """
    st.markdown("### 📋 Ventas Registradas")
    
    ventas = p.get("ventas_diarias", [])
    
    if not ventas:
        st.info("💡 No hay ventas registradas para este período aún. Utiliza el formulario a la izquierda para agregar registros.")
        return
 
    # Construir DataFrame. BUG-04 FIX: ordenar por fecha descendente (más recientes arriba)
    df = pd.DataFrame(ventas)
    # BUG-07 FIX: errors='coerce' previene crash si hay fechas vacías o malformadas desde Sheets
    df["_fecha_ord"] = pd.to_datetime(df["fecha"], errors="coerce")
    df = df.sort_values("_fecha_ord", ascending=False).drop(columns=["_fecha_ord"])
    df["Monto"] = df["monto"].apply(format_currency)
    df["Fecha"] = pd.to_datetime(df["fecha"], errors="coerce").dt.strftime("%d/%m/%Y").fillna("Sin fecha")
    df = df.rename(columns={"nota": "Descripción / Nota"})
    
    df_visual = df[["Fecha", "Monto", "Descripción / Nota"]]
    df_visual.index = range(1, len(df_visual) + 1)
    
    st.dataframe(df_visual, use_container_width=True)
    
    total_ventas = sum(v["monto"] for v in ventas)
    st.markdown(
        f"**Resumen Período:** `{len(ventas)}` registros | "
        f"**Total Acumulado:** `{format_currency(total_ventas)}`"
    )
 
    with st.expander("🗑️ Eliminar Registro de Venta", expanded=False):
        # DEEP-04 FIX: ordenar ventas por fecha descendente para que los índices #1, #2 correspondan con la visual
        ventas_ordenadas = sorted(
            ventas, 
            key=lambda x: pd.to_datetime(x["fecha"], errors="coerce") if pd.to_datetime(x["fecha"], errors="coerce") is not pd.NaT else pd.Timestamp.min, 
            reverse=True
        )
        
        venta_options = {
            v["id"]: f"#{i+1} - {pd.to_datetime(v['fecha'], errors='coerce').strftime('%d/%m/%Y') if pd.to_datetime(v['fecha'], errors='coerce') is not pd.NaT else 'Sin fecha'} | {format_currency(v['monto'])} ({v['nota']})" 
            for i, v in enumerate(ventas_ordenadas)
        }
        
        venta_id_to_delete = st.selectbox(
            "Seleccione la venta a eliminar:", 
            options=list(venta_options.keys()), 
            format_func=lambda x: venta_options[x]
        )
        
        if st.button("❌ Eliminar Venta Seleccionada", type="primary", use_container_width=True):
            p["ventas_diarias"] = [v for v in p["ventas_diarias"] if v["id"] != venta_id_to_delete]
            
            # Guardado local
            save_current_period(p)
            
            # Sincronización de eliminación
            if is_sheets_active():
                with st.spinner("Sincronizando eliminación con Google Sheets..."):
                    sync_all_sales_to_sheets(p["ventas_diarias"], p)
                    
            st.success("Registro de venta eliminado correctamente.")
            st.rerun()
