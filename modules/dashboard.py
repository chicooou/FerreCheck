"""
Módulo Dashboard de FerreCheck.
Presenta los KPIs principales, alertas inteligentes, la barra de progreso del semáforo
y el panel ejecutivo de Utilidad Real segmentada por Modalidad de Pago.
v2: Incorpora desglose de Utilidad Real vs. Compromisos Futuros con fechas de vencimiento exactas.
"""

import streamlit as st
import textwrap
from config import format_currency, ESTRATEGIAS, MESES, get_month_name
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
    Renderiza las métricas clave, el semáforo financiero, el desglose de Utilidad Real
    y la proyección de compromisos futuros por fecha de vencimiento.
    """
    # 1. Cabecera con Badge de Estrategia Activa
    est_info = ESTRATEGIAS.get(p["estrategia"], ESTRATEGIAS["balance"])
    st.markdown(
        textwrap.dedent(f"""
        <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 15px;">
            <h3 style="margin: 0; font-size: 20px; font-weight: 600; color: #FFFFFF;">📊 Estado de Flujo de Caja</h3>
            <span class="strategy-badge strategy-badge-{p['estrategia']}">{est_info['nombre']}</span>
        </div>
        """),
        unsafe_allow_html=True
    )

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
        util = calc_results["utilidad_real"]
        icono_util = "📈" if util >= 0 else "📉"
        st.markdown(
            render_kpi_card(
                "Utilidad Real del Mes",
                format_currency(util),
                icono_util,
                "Ventas menos Gastos Fijos, compras al Contado, créditos vencidos este mes y deudas heredadas. "
                "Las compras a crédito con vencimiento futuro NO se descuentan aquí."
            ),
            unsafe_allow_html=True
        )

    st.write("")

    # 2. Alertas Inteligentes de Seguridad Financiera (Ancho Completo)
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

    # 3. Diseño Grid: Dos Columnas Principales
    col_semaforos, col_desglose = st.columns([11, 9], gap="large")

    with col_semaforos:
        st.markdown("### 🚦 Semáforo de Consumo Presupuestario")

        consumo_pct = calc_results["consumo_pct"]
        total_compras = calc_results["total_compras"]
        limite_real = calc_results["limite_real"]
        semaforo = obtener_estado_semaforo(consumo_pct)

        nombre_mes_actual = f"{get_month_name(p['mes'])} {p['ano']}"
        libre_actual = limite_real - total_compras
        if libre_actual >= 0:
            texto_libre_actual = f" (<b>{format_currency(libre_actual)}</b> libre)"
        else:
            texto_libre_actual = f" (<b>{format_currency(abs(libre_actual))}</b> excedido ⚠️)"

        # Barra 2: Pagos del Mes Actual (Contado + Deudas Heredadas)
        util_data = calc_results.get("util_modalidad", {})
        total_pagos = util_data.get("egreso_real_mes", 0.0)
        consumo_pagos_pct = 0.0
        if limite_real > 0:
            consumo_pagos_pct = (total_pagos / limite_real) * 100.0
        elif total_pagos > 0:
            consumo_pagos_pct = 100.0
            
        semaforo_pagos = obtener_estado_semaforo(consumo_pagos_pct)
        libre_pagos = limite_real - total_pagos
        if libre_pagos >= 0:
            texto_libre_pagos = f" (<b>{format_currency(libre_pagos)}</b> libre)"
        else:
            texto_libre_pagos = f" (<b>{format_currency(abs(libre_pagos))}</b> excedido ⚠️)"

        # Mapeo del estado de alerta para estilo CSS
        alert_class = "alert-info"
        alert_style = ""
        if semaforo["status"] == "success":
            alert_style = "background: rgba(9, 171, 59, 0.1); border: 1px solid rgba(9, 171, 59, 0.2); color: #09AB3B;"
        elif semaforo["status"] == "warning":
            alert_class = "alert-warning"
        elif semaforo["status"] == "error":
            alert_class = "alert-danger"

        texto_alerta = f"<b>Estado Compras del Mes: {semaforo['emoji']} {semaforo['color']}</b> — {semaforo['mensaje']}"

        # Card 1: Operación en Curso (Hoy)
        st.markdown(
            textwrap.dedent(f"""
            <div class="dashboard-card">
                <h4 style="margin-top:0; margin-bottom:15px; color:#FFFFFF; font-size:16px; font-weight:600; display:flex; align-items:center; gap:8px;">
                    🎯 Operación en Curso ({nombre_mes_actual})
                </h4>
                
                <!-- Barra 1: Compras -->
                <div class="progress-container" style="margin-top: 5px; margin-bottom: 12px;">
                    <div class="progress-header">
                        <span class="progress-title">🚦 Compras: <b>{format_currency(total_compras)}</b> de <b>{format_currency(limite_real)}</b>{texto_libre_actual}</span>
                        <span class="progress-percentage" style="color: {semaforo['hex']};">{consumo_pct:.1f}% Consumido</span>
                    </div>
                    <div style="background-color: rgba(255,255,255,0.1); border-radius: 10px; height: 16px; width: 100%; overflow: hidden;">
                        <div style="background-color: {semaforo['hex']}; width: {min(consumo_pct, 100)}%; height: 100%; border-radius: 10px; transition: width 0.5s ease-in-out;"></div>
                    </div>
                </div>
                
                <!-- Alerta de Semáforo -->
                <div class="alert-box {alert_class}" style="{alert_style} margin-bottom: 18px;">
                    {semaforo['emoji']} {texto_alerta}
                </div>
                
                <!-- Barra 2: Pagos -->
                <div class="progress-container" style="border: 1px dashed rgba(255,255,255,0.15); margin-bottom: 5px; padding: 12px; border-radius: 8px; background-color: rgba(255,255,255,0.02);">
                    <div class="progress-header" style="margin-bottom: 8px;">
                        <span class="progress-title" style="color: #E2E8F0; font-size: 14px;">💵 Pagos de este Mes (Contado + Deudas Heredadas): <b>{format_currency(total_pagos)}</b> de <b>{format_currency(limite_real)}</b>{texto_libre_pagos}</span>
                        <span class="progress-percentage" style="color: {semaforo_pagos['hex']}; font-weight: 600; font-size: 14px;">{consumo_pagos_pct:.1f}% Pagado</span>
                    </div>
                    <div style="background-color: rgba(255,255,255,0.1); border-radius: 10px; height: 12px; width: 100%; overflow: hidden;">
                        <div style="background-color: {semaforo_pagos['hex']}; width: {min(consumo_pagos_pct, 100)}%; height: 100%; border-radius: 10px; transition: width 0.5s ease-in-out;"></div>
                    </div>
                </div>
            </div>
            """),
            unsafe_allow_html=True
        )

        # Card 2: Planificación de Pagos Futuros (Predictivos)
        render_barras_predictivas(calc_results)

        # Historial madurez info box
        madurez = calc_results.get("madurez_historial")
        if madurez and madurez.get("puede_usar_promedio"):
            n = madurez["periodos_cerrados"]
            st.info(
                f"💡 **¡Ya tienes {n} meses de historial!** Las proyecciones de pagos futuros "
                f"pueden ser más precisas usando un promedio histórico de ventas en lugar de la "
                f"extrapolación de Caja Diaria. Esta función estará disponible próximamente."
            )

    with col_desglose:
        st.markdown("### 💰 Análisis y Desglose")

        util_data = calc_results.get("util_modalidad", {})
        if not util_data:
            st.info("Sin datos de modalidad disponibles.")
        else:
            # Desglose de egresos en cuadrícula 2x2
            st.markdown("#### ✅ Egresos que Impactan ESTE Mes")
            
            grid_row1_col1, grid_row1_col2 = st.columns(2)
            with grid_row1_col1:
                st.markdown(
                    render_kpi_card(
                        "Compras al Contado",
                        format_currency(util_data.get("egreso_contado", 0)),
                        "💵",
                        "Efectivo que ya salió de la cuenta bancaria este mes."
                    ),
                    unsafe_allow_html=True
                )
            with grid_row1_col2:
                st.markdown(
                    render_kpi_card(
                        "Créditos a Vencer",
                        format_currency(util_data.get("egreso_credito_mes_actual", 0)),
                        "📅",
                        "Compras a crédito cuya fecha de pago cae dentro de este mismo mes."
                    ),
                    unsafe_allow_html=True
                )

            grid_row2_col1, grid_row2_col2 = st.columns(2)
            with grid_row2_col1:
                st.markdown(
                    render_kpi_card(
                        "Deudas Heredadas",
                        format_currency(util_data.get("egreso_deudas_heredadas", 0)),
                        "📥",
                        "Créditos de meses anteriores que vencen en este período."
                    ),
                    unsafe_allow_html=True
                )
            with grid_row2_col2:
                egreso_real = util_data.get("egreso_real_mes", 0)
                st.markdown(
                    render_kpi_card(
                        "Total Egreso Real",
                        format_currency(egreso_real),
                        "🏦",
                        "Suma total de todos los egresos que impactan la utilidad de este mes."
                    ),
                    unsafe_allow_html=True
                )

            # Detalle de deudas heredadas expander
            deudas_heredadas = util_data.get("deudas_heredadas", [])
            if deudas_heredadas:
                with st.expander("📥 Ver detalle de Deudas Heredadas", expanded=False):
                    for d in deudas_heredadas:
                        from config import get_month_name as gmn
                        origen = f"{gmn(d.get('origen_mes', 0))} {d.get('origen_ano', '')}"
                        veces = d.get("veces_postergada", 0)
                        postponed_label = f" ⚠️ Postergada {veces}x" if veces > 0 else ""
                        st.markdown(
                            f"• **{d.get('proveedor', '?')}** — {format_currency(d.get('monto', 0))} "
                            f"({d.get('modalidad_original', '?')} de {origen}){postponed_label}"
                        )

            # Expander explicativo de fórmula
            with st.expander("💡 ¿Cómo se calcula la Utilidad Real?", expanded=False):
                st.markdown(f"""
                Para darte un número exacto y real, solo restamos el dinero que **efectivamente salió de tu bolsa este mes**.
                
                **Fórmula:**
                * **Ventas:** `+ {format_currency(p['ventas'])}`
                * **Gastos Fijos:** `- {format_currency(calc_results['gastos_totales'])}`
                * **Compras al Contado:** `- {format_currency(calc_results.get('util_modalidad', {}).get('egreso_contado', 0))}`
                * **Créditos a Vencer este Mes:** `- {format_currency(calc_results.get('util_modalidad', {}).get('egreso_credito_mes_actual', 0))}`
                * **Deudas Heredadas:** `- {format_currency(calc_results.get('util_modalidad', {}).get('egreso_deudas_heredadas', 0))}`
                ---
                * **= Utilidad Real:** `{format_currency(util)}`
                
                *(Las compras a crédito a 30, 45 o 60 días no se restan aquí porque las pagarás en meses futuros).*
                """)

            # Compromisos futuros (si hay deudas futuras a mediano plazo)
            compromisos = util_data.get("compromisos_total_futuro", 0)
            if compromisos > 0:
                st.markdown("#### ⏳ Compromisos Futuros *(fuera de este mes)*")
                
                col_f1, col_f2 = st.columns(2)
                mes_sig = p["mes"] + 1
                ano_sig = p["ano"]
                if mes_sig > 12:
                    mes_sig = 1
                    ano_sig += 1

                with col_f1:
                    st.markdown(
                        render_kpi_card(
                            f"Vencen en {get_month_name(mes_sig)}",
                            format_currency(util_data.get("compromisos_mes_siguiente", 0)),
                            "🗓️",
                            f"Créditos cuya fecha de pago cae en el mes de {get_month_name(mes_sig)}."
                        ),
                        unsafe_allow_html=True
                    )
                with col_f2:
                    st.markdown(
                        render_kpi_card(
                            "Vencen en Mes+2 o más",
                            format_currency(util_data.get("compromisos_mes_2_plus", 0)),
                            "🗓️",
                            "Créditos con vencimiento en dos o más meses."
                        ),
                        unsafe_allow_html=True
                    )

                # Detalle de compromisos futuros
                detalle = util_data.get("detalle_compromisos_futuros", [])
                if detalle:
                    with st.expander("📋 Ver detalle de compromisos futuros", expanded=False):
                        for comp in sorted(detalle, key=lambda x: (x["ano_vencimiento"], x["mes_vencimiento"])):
                            mes_v = get_month_name(comp["mes_vencimiento"])
                            ano_v = comp["ano_vencimiento"]
                            st.markdown(
                                f"• **{comp['proveedor']}** — {format_currency(comp['monto'])} "
                                f"({comp['modalidad']}, compra {comp['fecha_compra']}) → "
                                f"**Vence: {mes_v} {ano_v}**"
                            )
            else:
                st.info("✅ No hay compromisos de crédito pendientes para meses futuros en este período.")


def render_barras_predictivas(calc_results: dict):
    """Renderiza las barras de compromisos futuros para Mes+1 y Mes+2 en formato de tarjeta premium."""
    proyeccion = calc_results.get("proyeccion_futura")
    if not proyeccion:
        return
    
    metodo = proyeccion["metodo_proyeccion"]
    ventas_proy = proyeccion["ventas_proyectadas"]
    
    # Nota informativa sobre cómo se calculó el límite
    if metodo == "caja_diaria":
        caption_text = (
            f"Límites proyectados basados en extrapolación de Caja Diaria "
            f"de este mes ({format_currency(ventas_proy)} estimados de venta)."
        )
    else:
        caption_text = (
            f"Límites basados en el campo Ventas del sidebar ({format_currency(ventas_proy)} base) "
            f"debido a que no hay registros en la Caja Diaria para extrapolar."
        )
        
    html = f"""
    <div class="dashboard-card">
        <h4 style="margin-top:0; margin-bottom:5px; color:#FFFFFF; font-size:16px; font-weight:600; display:flex; align-items:center; gap:8px;">
            📅 Compromisos de Pago Futuros (Proyección)
        </h4>
        <p style="color: #8C9CAE; font-size: 12px; margin-top: 0; margin-bottom: 15px;">
            ℹ️ {caption_text}
        </p>
    """
    
    for key in ["mes_1", "mes_2"]:
        data = proyeccion[key]
        semaforo = data["semaforo"]
        pct = data["consumo_pct"]
        
        # Calcular saldo libre proyectado
        libre = data["limite_proyectado"] - data["comprometido"]
        if libre >= 0:
            texto_libre = f" (<b>{format_currency(libre)}</b> libre)"
        else:
            texto_libre = f" (<b>{format_currency(abs(libre))}</b> excedido ⚠️)"
        
        html += f"""
        <div class="progress-container" style="border: 1px dashed rgba(255,255,255,0.15); 
             margin-top: 10px; margin-bottom: 10px; padding: 12px; border-radius: 8px; background-color: rgba(255,255,255,0.02);">
            <div class="progress-header" style="margin-bottom: 8px;">
                <span class="progress-title" style="color: #E2E8F0; font-size: 14px;">
                    📅 Pagos de <b>{data['nombre']}</b>: 
                    <b>{format_currency(data['comprometido'])}</b> de un límite proyectado de <b>{format_currency(data['limite_proyectado'])}</b>
                    {texto_libre}
                </span>
                <span class="progress-percentage" style="color: {semaforo['hex']}; font-weight: 600; font-size: 14px;">
                    {pct:.1f}% Pagado
                </span>
            </div>
            <div style="background-color: rgba(255,255,255,0.1); border-radius: 10px; 
                        height: 12px; width: 100%; overflow: hidden;">
                <div style="background-color: {semaforo['hex']}; 
                     width: {min(pct, 100)}%; height: 100%; border-radius: 10px; 
                     transition: width 0.5s ease-in-out;"></div>
            </div>
        </div>
        """
        
        # Expander HTML con detalle de proveedores (usando <details>)
        if data["detalle"]:
            html += f"""
            <details style="margin-top: 5px; margin-bottom: 12px; margin-left: 5px;">
                <summary style="cursor: pointer; font-size: 13px; color: #8C9CAE; font-weight: 500; outline: none; user-select: none;">
                    📋 Ver detalle de compromisos para {data['nombre']}
                </summary>
                <div style="padding: 8px 12px; margin-top: 5px; background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.05); border-radius: 6px; font-size: 13px; color: #E2E8F0;">
            """
            for d in data["detalle"]:
                html += f"<div style='margin-bottom: 4px;'>• <b>{d['proveedor']}</b> — {format_currency(d['monto'])} ({d.get('modalidad', '?')})</div>"
            html += """
                </div>
            </details>
            """
            
    html += "</div>"
    st.markdown(textwrap.dedent(html), unsafe_allow_html=True)
