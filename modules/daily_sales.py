"""
Módulo de Gestión de Caja Diaria (Ingresos Totales por Día) para FerreCheck.
Maneja el registro, validación, tabla visual, analíticas y sincronización en la nube y local.
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
    """Calcula el total acumulado de caja diaria del período actual."""
    return sum(v["monto"] for v in p.get("ventas_diarias", []))

def render_sales_kpis(p: dict):
    """
    Renderiza tarjetas KPI para comparar el total de caja diaria acumulada
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
                    📈 Caja Diaria Acumulada ({get_month_name(p['mes'])})
                </span>
                <h2 style="margin: 5px 0 0 0; color: #FFFFFF; font-size: 28px; font-weight: 700;">
                    {format_currency(total_diario)}
                </h2>
                <p style="margin: 5px 0 0 0; font-size: 12px; color: #8C9CAE;">
                    Suma total de los montos diarios de caja ingresados este mes.
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
    Renderiza el formulario para registrar el ingreso de caja de un día.
    """
    st.markdown("### 📝 Registrar Caja del Día")
    
    primer_dia = datetime.date(p["ano"], p["mes"], 1)
    ultimo_dia = datetime.date(p["ano"], p["mes"], get_last_day_of_month(p["ano"], p["mes"]))
    
    hoy = datetime.date.today()
    fecha_defecto = hoy if primer_dia <= hoy <= ultimo_dia else primer_dia

    with st.form("form_nueva_venta", clear_on_submit=True):
        col_monto, col_fecha = st.columns([1, 1])
        with col_monto:
            monto = st.number_input("Ingreso Total del Día (Q)", min_value=0.0, step=100.0, format="%f")
        with col_fecha:
            fecha_seleccionada = st.date_input(
                "Fecha del Registro", 
                value=fecha_defecto,
                min_value=primer_dia,
                max_value=ultimo_dia
            )
            
        nota = st.text_input("Nota / Descripción (Opcional)", placeholder="Ej. Día normal, Promoción de fin de semana, Día lento por lluvia")
        
        import html
        nota_sanitizada = html.escape(nota.strip()) if nota else "Sin descripción"
        nota_sanitizada = nota_sanitizada.replace('"', '&quot;').replace("'", '&#x27;')
            
        submitted = st.form_submit_button("💾 Registrar Caja del Día", use_container_width=True)
        
        if submitted:
            if monto <= 0:
                st.error("⚠️ El monto del ingreso diario debe ser mayor a cero.")
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
            
            st.success(f"✅ Caja registrada correctamente: {format_currency(monto)} en fecha {nueva_venta['fecha']}")
            st.rerun()
 
def render_daily_sales_table(p: dict):
    """
    Muestra la tabla de los ingresos de caja diaria registrados y la sección para eliminar registros.
    """
    st.markdown("### 📋 Registro de Ingresos Diarios")
    
    ventas = p.get("ventas_diarias", [])
    
    if not ventas:
        st.info("💡 No hay registros de caja para este período aún. Utiliza el formulario a la izquierda para agregar registros.")
        return
 
    # Construir DataFrame
    df = pd.DataFrame(ventas)
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
        f"**Resumen Período:** `{len(ventas)}` días registrados | "
        f"**Total Acumulado:** `{format_currency(total_ventas)}`"
    )
 
    with st.expander("🗑️ Eliminar Registro del Día", expanded=False):
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
            "Seleccione el día a eliminar:", 
            options=list(venta_options.keys()), 
            format_func=lambda x: venta_options[x]
        )
        
        if st.button("❌ Eliminar Registro de Caja", type="primary", use_container_width=True):
            p["ventas_diarias"] = [v for v in p["ventas_diarias"] if v["id"] != venta_id_to_delete]
            
            # Guardado local
            save_current_period(p)
            
            # Sincronización de eliminación
            if is_sheets_active():
                with st.spinner("Sincronizando eliminación con Google Sheets..."):
                    sync_all_sales_to_sheets(p["ventas_diarias"], p)
                    
            st.success("Registro de caja eliminado correctamente.")
            st.rerun()

def render_analytics_panel(p: dict):
    """
    Renderiza un panel de analíticas avanzadas basado en los ingresos de caja diaria.
    """
    st.write("---")
    st.markdown("### 📊 Analíticas e Insights de Caja")
    ventas = p.get("ventas_diarias", [])
    
    if len(ventas) < 2:
        st.info("💡 Se necesitan al menos **2 días registrados** para generar promedios, tendencias y proyecciones de caja.")
        return
        
    df = pd.DataFrame(ventas)
    df["monto"] = df["monto"].astype(float)
    df["fecha_dt"] = pd.to_datetime(df["fecha"], errors="coerce")
    
    # 1. Cálculos de métricas core
    total_acumulado = df["monto"].sum()
    cantidad_dias = len(df)
    promedio_diario = total_acumulado / cantidad_dias
    
    idx_max = df["monto"].idxmax()
    monto_max = df.loc[idx_max, "monto"]
    fecha_max = pd.to_datetime(df.loc[idx_max, "fecha"]).strftime("%d/%m/%Y")
    
    idx_min = df["monto"].idxmin()
    monto_min = df.loc[idx_min, "monto"]
    fecha_min = pd.to_datetime(df.loc[idx_min, "fecha"]).strftime("%d/%m/%Y")
    
    # Días totales del mes
    dias_del_mes = get_last_day_of_month(p["ano"], p["mes"])
    completitud_pct = (cantidad_dias / dias_del_mes) * 100
    
    # 2. Proyección de cierre de mes
    proyeccion_cierre = promedio_diario * dias_del_mes
    
    # 3. Variación vs mes anterior
    ventas_base = p.get("ventas", 0.0)
    if ventas_base > 0:
        variacion_pct = ((proyeccion_cierre - ventas_base) / ventas_base) * 100
        variacion_str = f"{variacion_pct:+.1f}% vs Mes Anterior"
    else:
        variacion_pct = 0.0
        variacion_str = "Sin datos de mes anterior"
        
    # Renderizar KPIs (2 filas de 3 columnas)
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(
            label="📊 Promedio Diario",
            value=format_currency(promedio_diario),
            help="El promedio facturado por día registrado en este período."
        )
    with col2:
        st.metric(
            label="🏆 Día Más Fuerte",
            value=format_currency(monto_max),
            delta=f"Fecha: {fecha_max}",
            delta_color="off"
        )
    with col3:
        st.metric(
            label="📉 Día Más Débil",
            value=format_currency(monto_min),
            delta=f"Fecha: {fecha_min}",
            delta_color="off"
        )
        
    col4, col5, col6 = st.columns(3)
    with col4:
        st.metric(
            label="📅 Cobertura de Registro",
            value=f"{cantidad_dias} / {dias_del_mes} días",
            delta=f"{completitud_pct:.1f}% del mes",
            delta_color="normal"
        )
    with col5:
        st.metric(
            label="🔮 Proyección Cierre de Mes",
            value=format_currency(proyeccion_cierre),
            help="Monto estimado que se alcanzará al finalizar el mes si se mantiene el promedio diario actual."
        )
    with col6:
        delta_color = "normal" if variacion_pct >= 0 else "inverse"
        st.metric(
            label="📈 Tendencia vs Mes Anterior",
            value=f"{variacion_pct:+.1f}%" if ventas_base > 0 else "N/A",
            delta=variacion_str if ventas_base > 0 else "Base de cálculo no definida",
            delta_color=delta_color
        )
        
    # Renderizar Gráfico de distribución de caja por día
    st.write(" ")
    st.markdown("#### 📈 Distribución de Caja Diaria por Fecha")
    
    # Crear un dataset ordenado por fecha cronológica para el gráfico
    df_chart = df.sort_values("fecha_dt")
    df_chart["Día"] = df_chart["fecha_dt"].dt.strftime("%d/%m")
    df_chart = df_chart.set_index("Día")
    
    # Gráfico de barras nativo de Streamlit
    st.bar_chart(df_chart["monto"], use_container_width=True)
