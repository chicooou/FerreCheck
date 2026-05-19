"""
Módulo Conector de Google Sheets para FerreCheck.
Permite lectura y escritura síncrona en tiempo real con Google Sheets,
con un sistema de tolerancia a fallos y fallback automático a JSON local.
Incluye soporte para modalidades de pago (Contado / Crédito).
Optimizado con @st.cache_resource para evitar cuelgues por rate-limiting de Google OAuth.
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

@st.cache_data(ttl=60, show_spinner=False)
def is_sheets_active() -> bool:
    """Retorna verdadero si las credenciales de Google Sheets están configuradas."""
    return get_google_creds() is not None

@st.cache_resource(show_spinner=False)
def get_gspread_client():
    """Autentica y retorna el cliente de gspread en caché para evitar cuelgues de OAuth."""
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
        return None

@st.cache_resource(show_spinner=False)
def get_cached_sheets(_client):
    """Obtiene y estructura las hojas de trabajo en caché para acceso instantáneo."""
    try:
        sh = _client.open(SPREADSHEET_NAME)
    except gspread.SpreadsheetNotFound:
        try:
            sh = _client.create(SPREADSHEET_NAME)
        except Exception:
            creds = get_google_creds()
            email = creds.get("client_email", "su-email-de-servicio@gserviceaccount.com")
            st.warning(
                f"⚠️ **Google Sheets Conectado pero falta compartir el archivo**\n\n"
                f"Tu aplicación arrancó en **Modo Local (Respaldo)** porque no pudo acceder al archivo `{SPREADSHEET_NAME}`.\n\n"
                f"**Para activar la sincronización en vivo:**\n"
                f"1. Crea una hoja de cálculo en tu Google Drive llamada exactamente: **`{SPREADSHEET_NAME}`**\n"
                f"2. Compártela como Editor con este correo:\n"
                f"   `{email}`\n"
                f"3. Recarga la página."
            )
            return None, None, None
            
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
        
    headers = ws_compras.row_values(1)
    if "modalidad" not in headers:
        try:
            ws_compras.update_cell(1, len(headers) + 1, "modalidad")
        except gspread.exceptions.APIError:
            ws_compras.add_cols(1)
            ws_compras.update_cell(1, len(headers) + 1, "modalidad")
            
    try:
        ws_ventas = sh.worksheet("VentasDiarias")
    except gspread.WorksheetNotFound:
        ws_ventas = sh.add_worksheet(title="VentasDiarias", rows="5000", cols="7")
        ws_ventas.append_row([
            "id", "ano", "mes", "fecha", "monto", "nota", "estado"
        ])
        
    return ws_periodos, ws_compras, ws_ventas

def get_or_init_sheets(client) -> tuple:
    """Envoltura para obtener las hojas cacheadas."""
    return get_cached_sheets(client)

def sync_period_to_sheets(p: dict, estado: str = "Activo"):
    """Guarda o actualiza la configuración de un período en la hoja de Google Sheets."""
    client = get_gspread_client()
    if not client:
        return
        
    try:
        res = get_or_init_sheets(client)
        if not res or res[0] is None:
            return
        ws_periodos = res[0]
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
        st.session_state.setdefault("sheets_sync_errors", []).append(f"sync_period: {str(e)}")

def sync_all_purchases_to_sheets(compras: list, p: dict, estado: str = "Activo"):
    """Sincroniza toda la lista de compras del período actual con la hoja de Google Sheets."""
    client = get_gspread_client()
    if not client:
        return
        
    try:
        res = get_or_init_sheets(client)
        if not res or res[0] is None:
            return
        ws_compras = res[1]
        all_rows = ws_compras.get_all_values()
        headers = all_rows[0]
        
        new_rows = [headers]
        for row in all_rows[1:]:
            if len(row) >= 8:
                # BUG-05 FIX: usar safe_int() en lugar de int() para tolerar celdas vacías
                if not (safe_int(row[1]) == int(p["ano"]) and safe_int(row[2]) == int(p["mes"]) and row[7] == "Activo"):
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
        # TECH-01 FIX: acumular errores en session_state en lugar de silenciarlos
        st.session_state.setdefault("sheets_sync_errors", []).append(f"sync_compras: {str(e)}")

def sync_all_sales_to_sheets(ventas_diarias: list, p: dict, estado: str = "Activo"):
    """Sincroniza toda la lista de ventas diarias del período actual con la hoja de Google Sheets."""
    client = get_gspread_client()
    if not client:
        return
        
    try:
        res = get_or_init_sheets(client)
        # BUG-02 FIX: verificar que res tiene 3 elementos antes de acceder a res[2]
        # Esto protege a usuarios que ya tenían la app con solo 2 hojas y cuyo caché aún no se ha invalidado
        if not res or len(res) < 3 or res[2] is None:
            return
        ws_ventas = res[2]
        all_rows = ws_ventas.get_all_values()
        
        if not all_rows:
            headers = ["id", "ano", "mes", "fecha", "monto", "nota", "estado"]
        else:
            headers = all_rows[0]
        
        new_rows = [headers]
        for row in all_rows[1:]:
            if len(row) >= 7:
                # BUG-05 FIX: usar safe_int() para tolerar celdas vacías o malformadas
                if not (safe_int(row[1]) == int(p["ano"]) and safe_int(row[2]) == int(p["mes"]) and row[6] == "Activo"):
                    new_rows.append(row)
                    
        for v in ventas_diarias:
            new_rows.append([
                v["id"],
                int(p["ano"]),
                int(p["mes"]),
                v["fecha"],
                float(v["monto"]),
                v["nota"],
                estado
            ])
            
        ws_ventas.clear()
        ws_ventas.update("A1", new_rows)
        
    except Exception as e:
        # TECH-01 FIX: acumular errores en session_state
        st.session_state.setdefault("sheets_sync_errors", []).append(f"sync_ventas_diarias: {str(e)}")

def close_period_in_sheets(p: dict):
    """Marca el período actual, sus compras y sus ventas como 'Cerrado' en Google Sheets."""
    sync_period_to_sheets(p, estado="Cerrado")
    sync_all_purchases_to_sheets(p["compras"], p, estado="Cerrado")
    ventas_diarias = p.get("ventas_diarias", [])
    sync_all_sales_to_sheets(ventas_diarias, p, estado="Cerrado")

def safe_float(val):
    if isinstance(val, str):
        val = val.replace("Q", "").replace(",", "").strip()
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0

def safe_int(val):
    if isinstance(val, str):
        val = val.replace(",", "").strip()
    try:
        return int(val)
    except (ValueError, TypeError):
        return 0

def load_all_data_from_sheets() -> tuple:
    """Carga todos los datos de Google Sheets reconstruyendo el estado con modalidades de pago."""
    client = get_gspread_client()
    if not client:
        return None, None
        
    try:
        res = get_or_init_sheets(client)
        if not res or res[0] is None:
            return None, None
        ws_periodos = res[0]
        ws_compras = res[1]
        
        # BUG-02 / DEEP-01 FIX: Guardia de longitud para evitar IndexError con caches viejos
        ws_ventas = res[2] if len(res) > 2 else None
        
        periodos_rows = ws_periodos.get_all_records()
        compras_rows = ws_compras.get_all_records()
        ventas_rows = ws_ventas.get_all_records() if ws_ventas is not None else []
        
        # PERF-04 FIX: Agrupar compras y ventas por (ano, mes) para optimizar complejidad de O(n^2) a O(n)
        from collections import defaultdict
        compras_por_periodo = defaultdict(list)
        for c in compras_rows:
            key = (safe_int(c.get("ano", 0)), safe_int(c.get("mes", 0)))
            compras_por_periodo[key].append({
                "id": str(c.get("id", "")),
                "monto": safe_float(c.get("monto", 0)),
                "proveedor": str(c.get("proveedor", "")),
                "fecha": str(c.get("fecha", "")),
                "nota": str(c.get("nota", "")),
                "modalidad": str(c.get("modalidad", "Contado")) if c.get("modalidad") else "Contado"
            })
            
        ventas_por_periodo = defaultdict(list)
        for v in ventas_rows:
            key = (safe_int(v.get("ano", 0)), safe_int(v.get("mes", 0)))
            ventas_por_periodo[key].append({
                "id": str(v.get("id", "")),
                "monto": safe_float(v.get("monto", 0)),
                "fecha": str(v.get("fecha", "")),
                "nota": str(v.get("nota", ""))
            })
            
        active_period = None
        history = {}
        
        for r in periodos_rows:
            ano_val = safe_int(r.get("ano", 0))
            mes_val = safe_int(r.get("mes", 0))
            period_key = (ano_val, mes_val)
            
            p_data = {
                "ano": ano_val,
                "mes": mes_val,
                "ventas": safe_float(r.get("ventas", 0)),
                "gastos": {
                    "planilla": safe_float(r.get("planilla", 0)),
                    "renta": safe_float(r.get("renta", 0)),
                    "luz": safe_float(r.get("luz", 0)),
                    "otros": safe_float(r.get("otros", 0))
                },
                "estrategia": str(r.get("estrategia", "balance")),
                "compras": compras_por_periodo.get(period_key, []),
                "ventas_diarias": ventas_por_periodo.get(period_key, [])
            }
            
            if r.get("estado") == "Activo":
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
                    "compras": p_data["compras"],
                    "ventas_diarias": p_data["ventas_diarias"]
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
                "compras": [],
                "ventas_diarias": []
            }
            sync_period_to_sheets(active_period, "Activo")
            
        return active_period, history
        
    except Exception as e:
        st.sidebar.error(f"❌ Error interno al cargar desde Google Sheets: {str(e)}")
        return None, None
