"""
Módulo de exportación de datos a CSV para FerreCheck.
"""

import streamlit as st
import pandas as pd
from config import get_month_name

def export_compras_csv(compras: list, p: dict) -> bytes:
    """
    Convierte la lista de compras del período actual a un archivo CSV codificado en bytes.
    Incluye información del período (Año, Mes) para un correcto histórico.
    """
    if not compras:
        return b""
        
    records = []
    for c in compras:
        records.append({
            "Año": p["ano"],
            "Mes": get_month_name(p["mes"]),
            "Fecha": c["fecha"],
            "Proveedor": c["proveedor"],
            "Monto": c["monto"],
            "Nota / Descripción": c["nota"]
        })
        
    df = pd.DataFrame(records)
    # Codificar a CSV UTF-8 con BOM para que Excel lea correctamente los tildes y caracteres en español
    csv_str = df.to_csv(index=False, encoding="utf-8-sig")
    return csv_str.encode("utf-8-sig")

def render_export_button(p: dict):
    """
    Renderiza el botón de exportación a CSV si existen compras registradas.
    """
    if not p["compras"]:
        return
        
    st.markdown("### 📥 Exportar Datos")
    csv_bytes = export_compras_csv(p["compras"], p)
    
    nombre_archivo = f"FerreCheck_Compras_{p['ano']}_{p['mes']:02d}.csv"
    
    st.download_button(
        label="📥 Descargar Historial de Compras (CSV)",
        data=csv_bytes,
        file_name=nombre_archivo,
        mime="text/csv",
        use_container_width=True,
        help="Descarga un archivo compatible con Excel con todas las compras de este mes."
    )
