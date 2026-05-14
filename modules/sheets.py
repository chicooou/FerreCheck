"""
Módulo Conector de Google Sheets para FerreCheck.
Permite lectura y escritura síncrona en tiempo real con Google Sheets,
con un sistema de tolerancia a fallos y fallback automático a JSON local.
Incluye soporte para modalidades de pago (Contado / Crédito).
"""

import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import os
import datetime

SPREADSHEET_NAME = "FerreCheck"

def get_google_creds():
    """
    Intenta obtener las credenciales de la cuenta de servicio de Google Cloud.
    Soporta TOML estructurado, cadenas JSON crudas o strings multi-línea.
    """
    if "google" in st.secrets and "service_account" in st.secrets["google"]:
        secret_val = st.secrets["google"]["service_account"]
        
        if isinstance(secret_val, str):
            try:
                return json.loads(secret_val)
            except Exception:
                pass
                
        try:
            return dict(secret_val)
        except Exception:
            pass
            
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
        sh = client.open(SPREADSHEET_NAME)
    except gspread.SpreadsheetNotFound:
        try:
            sh = client.create(SPREADSHEET_NAME)
        except Exception:
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
        ws_compras = sh.add_worksheet(title="Compras", rows="5000", cols="9")
        ws_compras.append_row([
            "id", "ano", "mes", "fecha", "proveedor", "monto", "nota", "estado", "modalidad"
        ])
        
    # Validar y asegurar que exista la columna modalidad en hojas existentes (retrocompatibilidad)
    headers = ws_compras.row_values(1)
    if "modalidad" not in headers:
        ws_compras.update_cell(1, len(headers) + 1, "modalidad")
        
    return ws_periodos, ws_compras

def sync_period_to_sheets(p: dict, estado: str = "Activo"):
    """Guarda o actualiza la configuración de un período en la hoja de Google Sheets."""
    client = get_gspread_client()
    if not client:
        return
        
    try:
        ws_periodos, _ = get_or_init_sheets(client)
        period_id = f"{p['ano']}_{p['mes']}"
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
            ws_periodos.update(f"A{cell.row}:J{cell.row}", [row_data])
        else:
            ws_periodos.append_row(row_data)
            
    except Exception as e:
        st.sidebar.warning(f"⚠️ Error al sincronizar período con Google Sheets: {str(e)}")

def sync_all_purchases_to_sheets(compras: list, p: dict, estado: str = "Activo"):
    """
    Sincroniza toda la lista de compras del período actual con la hoja de Google Sheets.
    Incluye la columna modalidad.
    """
    client = get_gspread_client()
    if not client:
        return
        
    try:
        _, ws_compras = get_or_init_sheets(client)
        all_rows = ws_compras.get_all_values()
        headers = all_rows[0]
        
        new_rows = [headers]
        for row in all_rows[1:]:
            if len(row) >= 8:
                if not (int(row[1]) == int(p["ano"]) and int(row[2]) == int(p["mes"]) and row[7] == "Activo"):
                    new_rows.append(row)
                    
        for c in compras:
            modalidad_val = c.get("modalidad", "Contado")
            new_rows.append([
                c["id"],
                int(p["ano"]),
                int(p["mes"]),
                c["fecha"],
                c["proveedor"],
                float(c["monto"]),
                c["nota"],
                estado,
                modalidad_val
            ])
            
        ws_compras.clear()
        ws_compras.update("A1", new_rows)
        
    except Exception as e:
        st.sidebar.warning(f"⚠️ Error al sincronizar compras con Google Sheets: {str(e)}")

def close_period_in_sheets(p: dict):
    """Marca el período actual y sus compras como 'Cerrado' en Google Sheets."""
    sync_period_to_sheets(p, estado="Cerrado")
    sync_all_purchases_to_sheets(p["compras"], p, estado="Cerrado")

def load_all_data_from_sheets() -> tuple:
    """
    Carga todos los datos de Google Sheets reconstruyendo el estado con modalidades de pago.
    """
    client = get_gspread_client()
    if not client:
        return None, None
        
    try:
        ws_periodos, ws_compras = get_or_init_sheets(client)
        periodos_rows = ws_periodos.get_all_records()
        compras_rows = ws_compras.get_all_records()
        
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
            
            for c in compras_rows:
                if int(c["ano"]) == p_data["ano"] and int(c["mes"]) == p_data["mes"]:
                    p_data["compras"].append({
                        "id": str(c["id"]),
                        "monto": float(c["monto"]),
                        "proveedor": str(c["proveedor"]),
                        "fecha": str(c["fecha"]),
                        "nota": str(c["nota"]),
                        "modalidad": str(c.get("modalidad", "Contado")) if c.get("modalidad") else "Contado"
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
            sync_period_to_sheets(active_period, "Activo")
            
        return active_period, history
        
    except Exception as e:
        st.sidebar.error(f"❌ Error al cargar datos desde Google Sheets: {str(e)}")
        return None, None
