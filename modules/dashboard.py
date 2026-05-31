"""
Módulo Dashboard de FerreCheck.
Presenta los KPIs principales, alertas inteligentes, la barra de progreso del semáforo
y el panel ejecutivo de Utilidad Real segmentada por Modalidad de Pago.
v2: Incorpora desglose de Utilidad Real vs. Compromisos Futuros con fechas de vencimiento exactas.
"""

import streamlit as st
import textwrap
from config import format_currency, ESTRATEGIAS, MESES, get_month_name, format_currency_clean
from modules.engine import obtener_estado_semaforo


def clean_html(html_str: str) -> str:
    """Elimina toda la de indentación de cada línea de la cadena HTML para evitar bloques de código Markdown."""
    lines = [line.strip() for line in html_str.strip().splitlines()]
    return "\n".join(lines)


def render_kpi_card(titulo: str, valor: str, icono: str, ayuda: str = "") -> str:
    """Retorna código HTML para una tarjeta KPI premium."""
    tooltip = f'title="{ayuda}"' if ayuda else ""
    return clean_html(f"""
    <div class="kpi-container" {tooltip}>
        <div class="kpi-title">{icono} {titulo}</div>
        <div class="kpi-value">{valor}</div>
    </div>
    """)


def render_dashboard(p: dict, calc_results: dict):
    """
    Renderiza las métricas clave, el semáforo financiero, el desglose de Utilidad Real
    y la proyección de compromisos futuros por fecha de vencimiento.
    """
    # 1. Cabecera con Badge de Estrategia Activa
    est_info = ESTRATEGIAS.get(p["estrategia"], ESTRATEGIAS["balance"])
    st.markdown(
        clean_html(f"""
        <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 15px;">
            <h3 style="margin: 0; font-size: 20px; font-weight: 600; color: #FFFFFF;">📊 Estado de Flujo de Caja</h3>
            <span class="strategy-badge strategy-badge-{p['estrategia']}">{est_info['nombre']}</span>
        </div>
        """),
        unsafe_allow_html=True
    )

    limite_texto = format_currency_clean(calc_results["limite_real"])
    if calc_results["fue_ajustado"]:
        limite_texto += " ⚠️"
        
    util = calc_results["utilidad_real"]
    icono_util = "📈" if util >= 0 else "📉"
    
    st.markdown(
        clean_html(f"""
        <div class="kpis-grid">
            {render_kpi_card("Ventas", format_currency_clean(p["ventas"]), "💵", "Ventas del mes inmediato anterior.")}
            {render_kpi_card("Gastos Fijos", format_currency_clean(calc_results["gastos_totales"]), "📋", "Suma de Planilla, Renta, Luz y Otros gastos recurrentes.")}
            {render_kpi_card("Límite de Compra", limite_texto, "🎯", "Presupuesto máximo de compras asignado al mes actual.")}
            {render_kpi_card("Utilidad Real del Mes", format_currency_clean(util), icono_util, "Ventas menos Gastos Fijos, compras al Contado, créditos vencidos este mes y deudas heredadas. Las compras a crédito con vencimiento futuro NO se descuentan aquí.")}
        </div>
        """),
        unsafe_allow_html=True
    )

    # 2. Alertas Inteligentes de Seguridad Financiera (Ancho Completo)
    if calc_results["fue_ajustado"]:
        if calc_results["saldo_disponible"] <= 0:
            st.error(
                f"🚨 **¡Bloqueo de Emergencia por Liquidez!** "
                f"El saldo disponible tras gastos fijos es de **{format_currency_clean(calc_results['saldo_disponible'])}**. "
                f"No puedes registrar compras para este período ya que no hay suficiente margen para cubrir tus costos fijos esenciales."
            )
        else:
            st.warning(
                f"⚠️ **Ajuste de Seguridad Activo:** El límite de compra sugerido original de **{format_currency_clean(calc_results['limite_sugerido'])}** "
                f"ha sido reajustado al 90% del saldo real disponible para garantizar la cobertura de tus gastos fijos. "
                f"Límite Seguro de Compra: **{format_currency_clean(calc_results['limite_real'])}**."
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
            texto_libre_actual_simple = f"{format_currency_clean(libre_actual)} libre"
        else:
            texto_libre_actual_simple = f"{format_currency_clean(abs(libre_actual))} excedido ⚠️"

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
            texto_libre_pagos_simple = f"{format_currency_clean(libre_pagos)} libre"
        else:
            texto_libre_pagos_simple = f"{format_currency_clean(abs(libre_pagos))} excedido ⚠️"

        # Card 1: Operación en Curso (Hoy)
        st.markdown(
            clean_html(f"""
            <div class="dashboard-card" style="padding: 16px;">
                <h4 style="margin-top:0; margin-bottom:12px; color:#FFFFFF; font-size:15px; font-weight:600; display:flex; align-items:center; gap:8px;">
                    🎯 Operación del Mes ({nombre_mes_actual})
                </h4>
                
                <!-- Barra 1: Compras -->
                <div style="margin-bottom: 12px;">
                    <div style="display:flex; justify-content:space-between; align-items:center; font-size:13px; margin-bottom:4px;">
                        <span style="color:#A0AEC0; font-weight:500;">🚦 Compras Realizadas ({semaforo['emoji']} {semaforo['color']})</span>
                        <span style="color:{semaforo['hex']}; font-weight:600;">{consumo_pct:.1f}%</span>
                    </div>
                    <div style="background-color: rgba(255,255,255,0.08); border-radius: 6px; height: 8px; width: 100%; overflow: hidden; margin-bottom: 4px;">
                        <div style="background-color: {semaforo['hex']}; width: {min(consumo_pct, 100)}%; height: 100%; border-radius: 6px;"></div>
                    </div>
                    <div style="display:flex; justify-content:space-between; font-size:11px; color:#8C9CAE;">
                        <span>{format_currency_clean(total_compras)} de {format_currency_clean(limite_real)}</span>
                        <span><b>{texto_libre_actual_simple}</b></span>
                    </div>
                </div>
                
                <hr style="border: 0; border-top: 1px solid rgba(255,255,255,0.08); margin: 12px 0;">
                
                <!-- Barra 2: Pagos -->
                <div>
                    <div style="display:flex; justify-content:space-between; align-items:center; font-size:13px; margin-bottom:4px;">
                        <span style="color:#A0AEC0; font-weight:500;">💵 Pagos de este Mes (Contado + Deudas)</span>
                        <span style="color:{semaforo_pagos['hex']}; font-weight:600;">{consumo_pagos_pct:.1f}%</span>
                    </div>
                    <div style="background-color: rgba(255,255,255,0.08); border-radius: 6px; height: 8px; width: 100%; overflow: hidden; margin-bottom: 4px;">
                        <div style="background-color: {semaforo_pagos['hex']}; width: {min(consumo_pagos_pct, 100)}%; height: 100%; border-radius: 6px;"></div>
                    </div>
                    <div style="display:flex; justify-content:space-between; font-size:11px; color:#8C9CAE;">
                        <span>{format_currency_clean(total_pagos)} de {format_currency_clean(limite_real)}</span>
                        <span><b>{texto_libre_pagos_simple}</b></span>
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
                        format_currency_clean(util_data.get("egreso_contado", 0)),
                        "💵",
                        "Efectivo que ya salió de la cuenta bancaria este mes."
                    ),
                    unsafe_allow_html=True
                )
            with grid_row1_col2:
                st.markdown(
                    render_kpi_card(
                        "Créditos a Vencer",
                        format_currency_clean(util_data.get("egreso_credito_mes_actual", 0)),
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
                        format_currency_clean(util_data.get("egreso_deudas_heredadas", 0)),
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
                        format_currency_clean(egreso_real),
                        "🏦",
                        "Suma total de todos los egresos que impactan la utilidad de este mes."
                    ),
                    unsafe_allow_html=True
                )

            # Detalle de deudas heredadas expander
            deudas_heredadas = util_data.get("deudas_heredadas", [])
            if deudas_heredadas:
                with st.expander("📥 Ver detalle de Deudas Heredadas", expanded=False):
                    html_deudas = '<div style="display: flex; flex-direction: column; gap: 6px; margin-top: 5px;">'
                    for d in deudas_heredadas:
                        from config import get_month_name as gmn
                        origen = f"{gmn(d.get('origen_mes', 0))} {d.get('origen_ano', '')}"
                        veces = d.get("veces_postergada", 0)
                        postponed_label = f" <span style='color:#FFC107;'>⚠️ Postergada {veces}x</span>" if veces > 0 else ""
                        monto_txt = format_currency_clean(d.get("monto", 0))
                        html_deudas += f"""
                        <div class="tx-item">
                            <div class="tx-info">
                                <span class="tx-name">{d.get('proveedor', '?')}{postponed_label}</span>
                                <span class="tx-meta">{d.get('modalidad_original', '?')} de {origen}</span>
                            </div>
                            <span class="tx-amount">{monto_txt}</span>
                        </div>
                        """
                    html_deudas += '</div>'
                    st.markdown(clean_html(html_deudas), unsafe_allow_html=True)

            # Expander explicativo de fórmula
            with st.expander("💡 ¿Cómo se calcula la Utilidad Real?", expanded=False):
                st.markdown(f"""
                Para darte un número exacto y real, solo restamos el dinero que **efectivamente salió de tu bolsa este mes**.
                
                **Fórmula:**
                * **Ventas:** `+ {format_currency_clean(p['ventas'])}`
                * **Gastos Fijos:** `- {format_currency_clean(calc_results['gastos_totales'])}`
                * **Compras al Contado:** `- {format_currency_clean(calc_results.get('util_modalidad', {}).get('egreso_contado', 0))}`
                * **Créditos a Vencer este Mes:** `- {format_currency_clean(calc_results.get('util_modalidad', {}).get('egreso_credito_mes_actual', 0))}`
                * **Deudas Heredadas:** `- {format_currency_clean(calc_results.get('util_modalidad', {}).get('egreso_deudas_heredadas', 0))}`
                ---
                * **= Utilidad Real:** `{format_currency_clean(util)}`
                
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
                            format_currency_clean(util_data.get("compromisos_mes_siguiente", 0)),
                            "🗓️",
                            f"Créditos cuya fecha de pago cae en el mes de {get_month_name(mes_sig)}."
                        ),
                        unsafe_allow_html=True
                    )
                with col_f2:
                    st.markdown(
                        render_kpi_card(
                            "Vencen en Mes+2 o más",
                            format_currency_clean(util_data.get("compromisos_mes_2_plus", 0)),
                            "🗓️",
                            "Créditos con vencimiento en dos o más meses."
                        ),
                        unsafe_allow_html=True
                    )

                # Detalle de compromisos futuros
                detalle = util_data.get("detalle_compromisos_futuros", [])
                if detalle:
                    with st.expander("📋 Ver detalle de compromisos futuros", expanded=False):
                        html_comp = '<div style="display: flex; flex-direction: column; gap: 6px; margin-top: 5px;">'
                        for comp in sorted(detalle, key=lambda x: (x["ano_vencimiento"], x["mes_vencimiento"])):
                            mes_v = get_month_name(comp["mes_vencimiento"])
                            ano_v = comp["ano_vencimiento"]
                            monto_txt = format_currency_clean(comp["monto"])
                            html_comp += f"""
                            <div class="tx-item">
                                <div class="tx-info">
                                    <span class="tx-name">{comp['proveedor']}</span>
                                    <span class="tx-meta">{comp['modalidad']} (compra {comp['fecha_compra']}) → <b>Vence: {mes_v} {ano_v}</b></span>
                                </div>
                                <span class="tx-amount">{monto_txt}</span>
                            </div>
                            """
                        html_comp += '</div>'
                        st.markdown(clean_html(html_comp), unsafe_allow_html=True)
            else:
                st.info("✅ No hay compromisos de crédito pendientes para meses futuros en este período.")


def render_barras_predictivas(calc_results: dict):
    """Renderiza las barras de compromisos futuros para Mes+1 y Mes+2 en formato de tarjeta premium compacta."""
    proyeccion = calc_results.get("proyeccion_futura")
    if not proyeccion:
        return
    
    metodo = proyeccion["metodo_proyeccion"]
    ventas_proy = proyeccion["ventas_proyectadas"]
    
    # Nota informativa corta sobre cómo se calculó el límite
    if metodo == "caja_diaria":
        caption_text = (
            f"Límites basados en extrapolación de Caja Diaria ({format_currency_clean(ventas_proy)} est. ventas)."
        )
    else:
        caption_text = (
            f"Límites basados en Ventas del sidebar ({format_currency_clean(ventas_proy)} base)."
        )
        
    html = f"""
    <div class="dashboard-card" style="padding: 16px;">
        <h4 style="margin-top:0; margin-bottom:12px; color:#FFFFFF; font-size:15px; font-weight:600; display:flex; align-items:center; gap:8px;">
            📅 Planificación de Pagos (Futuro)
        </h4>
    """
    
    keys = ["mes_1", "mes_2"]
    for i, key in enumerate(keys):
        data = proyeccion[key]
        semaforo = data["semaforo"]
        pct = data["consumo_pct"]
        
        # Calcular saldo libre proyectado
        libre = data["limite_proyectado"] - data["comprometido"]
        if libre >= 0:
            texto_libre = f"{format_currency_clean(libre)} libre"
        else:
            texto_libre = f"{format_currency_clean(abs(libre))} excedido ⚠️"
            
        details_html = ""
        # Expander HTML con detalle de proveedores (usando <details>)
        if data["detalle"]:
            details_html = f"""
            <details style="margin-top: 6px; margin-bottom: 6px; margin-left: 2px;">
                <summary style="cursor: pointer; font-size: 12px; color: #8C9CAE; font-weight: 500; outline: none; user-select: none;">
                    📋 Ver detalle de compromisos para {data['nombre']}
                </summary>
                <div style="display: flex; flex-direction: column; gap: 6px; margin-top: 8px; padding-left: 4px;">
            """
            for d in data["detalle"]:
                monto_txt = format_currency_clean(d["monto"])
                details_html += f"""
                <div class="tx-item" style="margin-bottom: 0;">
                    <div class="tx-info">
                        <span class="tx-name">{d['proveedor']}</span>
                        <span class="tx-meta">{d.get('modalidad', '?')}</span>
                    </div>
                    <span class="tx-amount">{monto_txt}</span>
                </div>
                """
            details_html += """
                </div>
            </details>
            """
            
        html += f"""
        <div>
            <div style="display:flex; justify-content:space-between; align-items:center; font-size:13px; margin-bottom:4px;">
                <span style="color:#A0AEC0; font-weight:500;">📅 Pagos {data['nombre']}</span>
                <span style="color:{semaforo['hex']}; font-weight:600;">{pct:.1f}% Pagado</span>
            </div>
            <div style="background-color: rgba(255,255,255,0.08); border-radius: 6px; height: 8px; width: 100%; overflow: hidden; margin-bottom: 4px;">
                <div style="background-color: {semaforo['hex']}; width: {min(pct, 100)}%; height: 100%; border-radius: 6px;"></div>
            </div>
            <div style="display:flex; justify-content:space-between; font-size:11px; color:#8C9CAE; margin-bottom: 4px;">
                <span>{format_currency_clean(data['comprometido'])} de {format_currency_clean(data['limite_proyectado'])}</span>
                <span><b>{texto_libre}</b></span>
            </div>
            {details_html}
        </div>
        """
        
        # Divider between mes_1 and mes_2
        if i < len(keys) - 1:
            html += '<hr style="border: 0; border-top: 1px solid rgba(255,255,255,0.08); margin: 12px 0;">'
            
    html += f"""
        <hr style="border: 0; border-top: 1px solid rgba(255,255,255,0.08); margin: 12px 0 8px 0;">
        <p style="color: #8C9CAE; font-size: 10px; margin-top: 0; margin-bottom: 0; font-style: italic;">
            * {caption_text}
        </p>
    </div>
    """
    st.markdown(clean_html(html), unsafe_allow_html=True)
