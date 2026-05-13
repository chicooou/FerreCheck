"""
Módulo Conector de Google Sheets para FerreCheck.
Permite lectura y escritura síncrona en tiempo real con Google Sheets,
con un sistema de tolerancia a fallos y fallback automático a JSON local.
"""

import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import os
import datetime

# Nombre del archivo de Google Sheets por defecto
SPREADSHEET_NAME = "FerreCheck"

def get_google_creds():
    """
    Intenta obtener las credenciales de la cuenta de servicio de Google Cloud.
    Primero busca en los secretos seguros de Streamlit, luego en el archivo local de desarrollo.
    """
    # 1. Buscar en Streamlit Secrets (Producción Cloud)
    if "google" in st.secrets and "service_account" in st.secrets["google"]:
        # st.secrets["google"]["service_account"] puede ser un dict directamente en TOML
        try:
            return dict(st.secrets["google"]["service_account"])
        except Exception:
            pass
            
    # 2. Buscar en archivo local para desarrollo
    local_creds_path = os.path.join("secrets", "google_sheets_creds.json")
    if os.path.exists(local_creds_path):
        try:
            with open(local_creds_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
            
    return None

def is_sheets_active() -> bool:
    """Retorna verdadero si las credenciales de Google Sheets están configuradas."""
    return get_google_creds() is not None

def get_gspread_client():
    """Autentica y retorna el cliente de gspread."""
    creds_dict = get_google_creds()
    if not creds_dict:
        return None
        
    scopes = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    try:
        credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        return gspread.authorize(credentials)
    except Exception as e:
        st.sidebar.error(f"Error de Autenticación de Google API: {str(e)}")
        return None

def get_or_init_sheets(client) -> tuple:
    """
    Busca la hoja de cálculo por nombre. Si no existe o no tiene acceso,
    guía al usuario con un mensaje instructivo.
    Retorna (sheet_periodos, sheet_compras).
    """
    try:
        # Intentar abrir la hoja de cálculo
        sh = client.open(SPREADSHEET_NAME)
    except gspread.SpreadsheetNotFound:
        # Intentar crearla si el Service Account tiene permisos de Drive
        try:
            sh = client.create(SPREADSHEET_NAME)
        except Exception:
            # Obtener email de la cuenta de servicio para que el usuario la comparta
            creds = get_google_creds()
            email = creds.get("client_email", "su-email-de-servicio@gserviceaccount.com")
            
            st.error(
                f"🛑 **No se encontró el archivo de Google Sheets '{SPREADSHEET_NAME}'**\n\n"
                f"Por favor, sigue estos pasos para activarlo:\n"
                f"1. Crea una hoja de cálculo en tu Google Drive llamada exactamente: **`{SPREADSHEET_NAME}`**\n"
                f"2. Haz clic en **Compartir** en la esquina superior derecha.\n"
                f"3. Comparte el archivo con el siguiente correo electrónico de servicio (permiso de Editor):\n"
                f"   `{email}`\n"
                f"4. Recarga esta página."
            )
            st.stop()
            
    # Asegurar que existan las hojas de trabajo "Periodos" y "Compras"
    try:
        ws_periodos = sh.worksheet("Periodos")
    except gspread.WorksheetNotFound:
        ws_periodos = sh.add_worksheet(title="Periodos", rows="1000", cols="10")
        ws_periodos.append_row([
            "id", "ano", "mes", "ventas", "planilla", "renta", "luz", "otros", "estrategia", "estado"
        ])
        
    try:
        ws_compras = sh.worksheet("Compras")
    except gspread.WorksheetNotFound:
        ws_compras = sh.add_worksheet(title="Compras", rows="5000", cols="8")
        ws_compras.append_row([
            "id", "ano", "mes", "fecha", "proveedor", "monto", "nota", "estado"
        ])
        
    return ws_periodos, ws_compras

def sync_period_to_sheets(p: dict, estado: str = "Activo"):
    """
    Guarda o actualiza la configuración de un período en la hoja de Google Sheets.
    """
    client = get_gspread_client()
    if not client:
        return
        
    try:
        ws_periodos, _ = get_or_init_sheets(client)
        
        # ID único por período (ej. "2026_5")
        period_id = f"{p['ano']}_{p['mes']}"
        
        # Buscar si ya existe la fila
        cell = ws_periodos.find(period_id, in_column=1)
        
        row_data = [
            period_id,
            int(p["ano"]),
            int(p["mes"]),
            float(p["ventas"]),
            float(p["gastos"]["planilla"]),
            float(p["gastos"]["renta"]),
            float(p["gastos"]["luz"]),
            float(p["gastos"]["otros"]),
            p["estrategia"],
            estado
        ]
        
        if cell:
            # Actualizar fila existente
            ws_periodos.update(f"A{cell.row}:J{cell.row}", [row_data])
        else:
            # Insertar nueva fila
            ws_periodos.append_row(row_data)
            
    except Exception as e:
        st.sidebar.warning(f"⚠️ Error al sincronizar período con Google Sheets: {str(e)}")

def sync_all_purchases_to_sheets(compras: list, p: dict, estado: str = "Activo"):
    """
    Sincroniza toda la lista de compras del período actual con la hoja de Google Sheets.
    Elimina registros anteriores activos para este período y escribe los nuevos.
    """
    client = get_gspread_client()
    if not client:
        return
        
    try:
        _, ws_compras = get_or_init_sheets(client)
        
        # Obtener todas las compras registradas
        all_rows = ws_compras.get_all_values()
        headers = all_rows[0]
        
        # Filtrar las filas para quedarnos solo con las que NO pertenecen a este período activo
        new_rows = [headers]
        for row in all_rows[1:]:
            if len(row) >= 8:
                # Si es de otro período o está cerrado, se queda
                if not (int(row[1]) == int(p["ano"]) and int(row[2]) == int(p["mes"]) and row[7] == "Activo"):
                    new_rows.append(row)
                    
        # Agregar los registros de compra actuales
        for c in compras:
            new_rows.append([
                c["id"],
                int(p["ano"]),
                int(p["mes"]),
                c["fecha"],
                c["proveedor"],
                float(c["monto"]),
                c["nota"],
                estado
            ])
            
        # Re-escribir la hoja completa de forma atómica para evitar desincronizaciones
        ws_compras.clear()
        ws_compras.update("A1", new_rows)
        
    except Exception as e:
        st.sidebar.warning(f"⚠️ Error al sincronizar compras con Google Sheets: {str(e)}")

def close_period_in_sheets(p: dict):
    """
    Marca el período actual y sus compras como 'Cerrado' en Google Sheets.
    """
    sync_period_to_sheets(p, estado="Cerrado")
    sync_all_purchases_to_sheets(p["compras"], p, estado="Cerrado")

def load_all_data_from_sheets() -> tuple:
    """
    Carga todos los datos de Google Sheets.
    Reconstruye el período operativo activo y el diccionario histórico.
    Retorna (periodo_actual, history_dict).
    """
    client = get_gspread_client()
    if not client:
        return None, None
        
    try:
        ws_periodos, ws_compras = get_or_init_sheets(client)
        
        # 1. Cargar Períodos
        periodos_rows = ws_periodos.get_all_records()
        # 2. Cargar Compras
        compras_rows = ws_compras.get_all_records()
        
        # Encontrar período activo
        active_period = None
        history = {}
        
        for r in periodos_rows:
            p_data = {
                "ano": int(r["ano"]),
                "mes": int(r["mes"]),
                "ventas": float(r["ventas"]),
                "gastos": {
                    "planilla": float(r["planilla"]),
                    "renta": float(r["renta"]),
                    "luz": float(r["luz"]),
                    "otros": float(r["otros"])
                },
                "estrategia": r["estrategia"],
                "compras": []
            }
            
            # Asociar compras a este período
            for c in compras_rows:
                if int(c["ano"]) == p_data["ano"] and int(c["mes"]) == p_data["mes"]:
                    p_data["compras"].append({
                        "id": str(c["id"]),
                        "monto": float(c["monto"]),
                        "proveedor": str(c["proveedor"]),
                        "fecha": str(c["fecha"]),
                        "nota": str(c["nota"])
                    })
                    
            if r["estado"] == "Activo":
                active_period = p_data
            else:
                yr_str = str(p_data["ano"])
                m_str = str(p_data["mes"])
                if yr_str not in history:
                    history[yr_str] = {}
                history[yr_str][m_str] = {
                    "ventas": p_data["ventas"],
                    "gastos": p_data["gastos"],
                    "estrategia": p_data["estrategia"],
                    "compras": p_data["compras"]
                }
                
        # Si no hay ningún período activo registrado en sheets, crear uno por defecto
        if not active_period:
            now = datetime.datetime.now()
            active_period = {
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
                "compras": []
            }
            # Guardarlo inmediatamente en Sheets
            sync_period_to_sheets(active_period, "Activo")
            
        return active_period, history
        
    except Exception as e:
        st.sidebar.error(f"❌ Error al cargar datos desde Google Sheets: {str(e)}")
        return None, None
