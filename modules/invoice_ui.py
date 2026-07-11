"""
Módulo de la interfaz de usuario en Streamlit para el flujo de Factura OCR e integración con Odoo.
"""

import streamlit as st
import pandas as pd
import os
import datetime
from typing import Dict, Any, List, Optional
from modules.odoo_connector import OdooRPC, OdooAuthError, OdooConnectionError, OdooValidationError
from modules.invoice_ocr import extract_invoice_data
from modules.rules_matrix import find_matching_rule, create_or_update_rule, load_processed_bill_ids, register_processed_bill_id

def get_odoo_client() -> Optional[OdooRPC]:
    """Crea una instancia del cliente Odoo utilizando las variables del entorno o st.secrets."""
    url = os.getenv("ODOO_URL") or st.secrets.get("ODOO_URL")
    db = os.getenv("ODOO_DB") or st.secrets.get("ODOO_DB")
    username = os.getenv("ODOO_USERNAME") or st.secrets.get("ODOO_USERNAME")
    api_key = os.getenv("ODOO_API_KEY") or st.secrets.get("ODOO_API_KEY")
    
    if not all([url, db, username, api_key]):
        return None
    return OdooRPC(url, db, username, api_key)

import math

def calculate_suggested_pvp(cost: float) -> float:
    margin = st.session_state.get("inv_suggested_margin", 30.0) / 100.0
    raw_pvp = cost * (1.0 + margin)
    
    rounding = st.session_state.get("inv_rounding_method", "ceil_integer")
    if rounding == "ceil_integer":
        return float(math.ceil(raw_pvp))
    elif rounding == "ceil_half":
        return float(math.ceil(raw_pvp * 2.0) / 2.0)
    return float(raw_pvp)

def initialize_state():
    """Inicializa todas las claves de session_state necesarias para el flujo de factura."""
    if "inv_step" not in st.session_state:
        st.session_state.inv_step = 1
    if "inv_vendor_id" not in st.session_state:
        st.session_state.inv_vendor_id = None
    if "inv_vendor_name" not in st.session_state:
        st.session_state.inv_vendor_name = ""
    if "inv_image_bytes" not in st.session_state:
        st.session_state.inv_image_bytes = None
    if "inv_extracted_data" not in st.session_state:
        st.session_state.inv_extracted_data = {}
    if "inv_edited_lines" not in st.session_state:
        st.session_state.inv_edited_lines = []
    if "inv_product_matches" not in st.session_state:
        st.session_state.inv_product_matches = []
    if "inv_invoice_number" not in st.session_state:
        st.session_state.inv_invoice_number = ""
    if "inv_invoice_date" not in st.session_state:
        st.session_state.inv_invoice_date = ""
    if "inv_po_result" not in st.session_state:
        st.session_state.inv_po_result = None
    if "inv_odoo_vendors" not in st.session_state:
        st.session_state.inv_odoo_vendors = []
    if "inv_odoo_taxes" not in st.session_state:
        st.session_state.inv_odoo_taxes = []
    if "inv_suggested_margin" not in st.session_state:
        st.session_state.inv_suggested_margin = 30.0
    if "inv_rounding_method" not in st.session_state:
        st.session_state.inv_rounding_method = "ceil_integer"
    if "inv_odoo_products" not in st.session_state:
        st.session_state.inv_odoo_products = []
    if "inv_odoo_connected" not in st.session_state:
        st.session_state.inv_odoo_connected = False
    if "inv_creating_po" not in st.session_state:
        st.session_state.inv_creating_po = False
    if "inv_rules_to_save" not in st.session_state:
        st.session_state.inv_rules_to_save = []
    
    # Odoo flow states
    if "inv_po_confirmed" not in st.session_state:
        st.session_state.inv_po_confirmed = False
    if "inv_picking_validated" not in st.session_state:
        st.session_state.inv_picking_validated = False
    if "inv_bill_id" not in st.session_state:
        st.session_state.inv_bill_id = None
    if "inv_bill_posted" not in st.session_state:
        st.session_state.inv_bill_posted = False
    if "inv_payment_registered" not in st.session_state:
        st.session_state.inv_payment_registered = False

def reset_flow():
    """Limpia el estado del flujo para procesar una nueva factura."""
    st.session_state.inv_step = 1
    st.session_state.inv_vendor_id = None
    st.session_state.inv_vendor_name = ""
    st.session_state.inv_image_bytes = None
    st.session_state.inv_extracted_data = {}
    st.session_state.inv_edited_lines = []
    st.session_state.inv_product_matches = []
    st.session_state.inv_invoice_number = ""
    st.session_state.inv_invoice_date = ""
    st.session_state.inv_po_result = None
    st.session_state.inv_creating_po = False
    st.session_state.inv_rules_to_save = []
    
    # Reset Odoo states
    st.session_state.inv_po_confirmed = False
    st.session_state.inv_picking_validated = False
    st.session_state.inv_bill_id = None
    st.session_state.inv_bill_posted = False
    st.session_state.inv_payment_registered = False

import json
import base64
import os

DRAFT_FILE = "data/draft_invoice.json"

def save_draft():
    """Guarda el estado actual de la factura en un archivo JSON local."""
    try:
        os.makedirs("data", exist_ok=True)
        img_b64 = None
        if st.session_state.inv_image_bytes:
            img_b64 = base64.b64encode(st.session_state.inv_image_bytes).decode('utf-8')
            
        draft_data = {
            "inv_step": st.session_state.inv_step,
            "inv_vendor_id": st.session_state.inv_vendor_id,
            "inv_vendor_name": st.session_state.inv_vendor_name,
            "inv_image_bytes_b64": img_b64,
            "inv_extracted_data": st.session_state.inv_extracted_data,
            "inv_edited_lines": st.session_state.inv_edited_lines,
            "inv_product_matches": st.session_state.inv_product_matches,
            "inv_invoice_number": st.session_state.inv_invoice_number,
            "inv_invoice_date": st.session_state.inv_invoice_date
        }
        with open(DRAFT_FILE, "w", encoding="utf-8") as f:
            json.dump(draft_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving draft: {e}")

def load_draft():
    """Carga el borrador guardado en el session_state."""
    try:
        if os.path.exists(DRAFT_FILE):
            with open(DRAFT_FILE, "r", encoding="utf-8") as f:
                draft_data = json.load(f)
                
            st.session_state.inv_step = draft_data.get("inv_step", 1)
            st.session_state.inv_vendor_id = draft_data.get("inv_vendor_id")
            st.session_state.inv_vendor_name = draft_data.get("inv_vendor_name", "")
            
            if draft_data.get("inv_image_bytes_b64"):
                st.session_state.inv_image_bytes = base64.b64decode(draft_data["inv_image_bytes_b64"])
            else:
                st.session_state.inv_image_bytes = None
                
            st.session_state.inv_extracted_data = draft_data.get("inv_extracted_data", {})
            st.session_state.inv_edited_lines = draft_data.get("inv_edited_lines", [])
            st.session_state.inv_product_matches = draft_data.get("inv_product_matches", [])
            st.session_state.inv_invoice_number = draft_data.get("inv_invoice_number", "")
            st.session_state.inv_invoice_date = draft_data.get("inv_invoice_date", "")
            return True
    except Exception as e:
        print(f"Error loading draft: {e}")
    return False

def clear_draft():
    """Elimina el borrador si la factura fue procesada con éxito."""
    try:
        if os.path.exists(DRAFT_FILE):
            os.remove(DRAFT_FILE)
    except Exception:
        pass

def render_rules_sidebar():
    with st.sidebar:
        st.markdown("---")
        st.markdown("### ⚙️ Reglas de Conversión")
        st.write("Reglas aprendidas al vincular descripciones de facturas con Odoo:")
        
        from modules.rules_matrix import load_rules, save_rules
        rules = load_rules()
        if not rules:
            st.info("Aún no tienes reglas guardadas.")
        else:
            rule_to_delete = None
            for r in rules:
                col_rule, col_del = st.columns([4, 1])
                with col_rule:
                    st.caption(f"**{r['vendor_name']}**")
                    st.write(f"*{r['original_description']}* ➔ **{r['converted_description']}**")
                with col_del:
                    if st.button("🗑️", key=f"del_rule_{r['id']}", help="Eliminar esta regla"):
                        rule_to_delete = r["id"]
                st.markdown("<hr style='margin: 4px 0px; border-color: rgba(49, 51, 63, 0.1);'>", unsafe_allow_html=True)
            
            if rule_to_delete:
                new_rules = [r for r in rules if r["id"] != rule_to_delete]
                save_rules(new_rules)
                st.success("Regla eliminada.")
                # Reset matches so it updates matches based on the new rules matrix
                st.session_state.inv_product_matches = []
                st.rerun()

def render_draft_manager():
    with st.expander("📁 Gestión de Borradores (Guardar / Cargar en PC)", expanded=False):
        st.write("Guarda o carga tu progreso en tu PC para no perder el trabajo.")
        
        col_down, col_up = st.columns(2)
        
        with col_down:
            st.markdown("#### Guardar Borrador")
            if st.button("💾 Preparar Borrador para Descarga", help="Guarda el estado actual antes de descargar"):
                save_draft()
                st.success("Borrador preparado.")
                
            if os.path.exists(DRAFT_FILE):
                with open(DRAFT_FILE, "r", encoding="utf-8") as f:
                    draft_content = f.read()
                st.download_button(
                    label="⬇️ Descargar Borrador a PC",
                    data=draft_content,
                    file_name="borrador_factura.json",
                    mime="application/json"
                )
                
        with col_up:
            st.markdown("#### Cargar Borrador")
            uploaded_draft = st.file_uploader("Selecciona un archivo .json", type=["json"], key="draft_uploader", label_visibility="collapsed")
            if uploaded_draft is not None:
                if st.button("📂 Restaurar desde archivo"):
                    try:
                        draft_data = json.load(uploaded_draft)
                        
                        st.session_state.inv_step = draft_data.get("inv_step", 1)
                        st.session_state.inv_vendor_id = draft_data.get("inv_vendor_id")
                        st.session_state.inv_vendor_name = draft_data.get("inv_vendor_name", "")
                        
                        if draft_data.get("inv_image_bytes_b64"):
                            st.session_state.inv_image_bytes = base64.b64decode(draft_data["inv_image_bytes_b64"])
                        else:
                            st.session_state.inv_image_bytes = None
                            
                        st.session_state.inv_extracted_data = draft_data.get("inv_extracted_data", {})
                        st.session_state.inv_edited_lines = draft_data.get("inv_edited_lines", [])
                        st.session_state.inv_product_matches = draft_data.get("inv_product_matches", [])
                        st.session_state.inv_invoice_number = draft_data.get("inv_invoice_number", "")
                        st.session_state.inv_invoice_date = draft_data.get("inv_invoice_date", "")
                        
                        with open(DRAFT_FILE, "w", encoding="utf-8") as f:
                            json.dump(draft_data, f, ensure_ascii=False, indent=2)
                            
                        st.success("Borrador restaurado con éxito.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error al leer el archivo: {e}")

def render_invoice_tab():
    render_rules_sidebar()
    render_draft_manager()
    initialize_state()

    st.markdown("## 📸 Integración Odoo — Facturación de Compra OCR")
    
    client = get_odoo_client()
    if not client:
        st.error(
            "🛑 Credenciales de Odoo incompletas en el archivo `.env`. "
            "Por favor, configure `ODOO_URL`, `ODOO_DB`, `ODOO_USERNAME` y `ODOO_API_KEY`."
        )
        return

    # Verificar / Cargar datos desde Odoo
    if not st.session_state.inv_odoo_connected:
        try:
            with st.spinner("Conectando con Odoo y obteniendo catálogo..."):
                client.connect()
                st.session_state.inv_odoo_vendors = client.fetch_vendors()
                st.session_state.inv_odoo_taxes = client.fetch_purchase_taxes()
                st.session_state.inv_odoo_products = client.fetch_all_products()
                st.session_state.inv_odoo_connected = True
        except Exception as e:
            st.error(f"⚠️ Error al conectar con Odoo: {str(e)}")
            if st.button("🔄 Intentar reconectar"):
                st.session_state.inv_odoo_connected = False
                st.rerun()
            return

    # Cabecera de estado
    col_status, col_refresh = st.columns([4, 1])
    with col_status:
        st.success(f"🟢 Conectado a Odoo SaaS | {len(st.session_state.inv_odoo_vendors)} proveedores, {len(st.session_state.inv_odoo_taxes)} impuestos y {len(st.session_state.inv_odoo_products)} productos cargados.")
    with col_refresh:
        if st.button("🔄 Sincronizar catálogo", use_container_width=True):
            st.session_state.inv_odoo_connected = False
            st.rerun()

    st.markdown("---")

    # Separar en dos sub-pestañas:
    subtab_ocr, subtab_payable = st.tabs(["📸 Procesar Factura (OCR)", "📊 Cuentas por Pagar (Odoo)"])

    with subtab_ocr:
        # Render de pasos
        if st.session_state.inv_step == 1:
            render_step_1(client)
        elif st.session_state.inv_step == 2:
            render_step_2()
        elif st.session_state.inv_step == 3:
            render_step_3(client)
        elif st.session_state.inv_step == 4:
            render_step_4(client)
        elif st.session_state.inv_step == 5:
            render_step_5(client)

    with subtab_payable:
        render_cuentas_por_pagar(client)

def render_step_1(client: OdooRPC):
    st.markdown("### Paso 1: Extracción de Datos")
    
    if os.path.exists(DRAFT_FILE) and st.session_state.inv_step == 1:
        st.info("Hay un borrador guardado de una sesión anterior.")
        if st.button("📝 Recuperar Borrador Anterior", type="primary"):
            if load_draft():
                st.success("Borrador recuperado con éxito.")
                st.rerun()

    st.write("Carga de Imagen")
    
    # Dropdown de proveedores
    vendors = st.session_state.inv_odoo_vendors
    vendor_options = {v['id']: v['name'] for v in vendors}
    
    selected_vendor_id = st.selectbox(
        "Selecciona el Proveedor:",
        options=list(vendor_options.keys()),
        format_func=lambda x: vendor_options[x],
        index=None if not st.session_state.inv_vendor_id else list(vendor_options.keys()).index(st.session_state.inv_vendor_id),
        placeholder="⚠️ Elige el proveedor de esta factura..."
    )
    
    if selected_vendor_id:
        st.session_state.inv_vendor_id = selected_vendor_id
        st.session_state.inv_vendor_name = vendor_options[selected_vendor_id]

    st.write("📸 Toma una foto o sube la factura de compra:")
    col_cam, col_file = st.columns([1, 1])
    
    with col_cam:
        cam_photo = st.camera_input("📷 Tomar foto (Ideal celular)")
        
    with col_file:
        uploaded_file = st.file_uploader(
            "📁 Subir archivo",
            type=["jpg", "jpeg", "png", "webp"],
            help="Selecciona un archivo de tu galería o PC."
        )

    final_file = cam_photo or uploaded_file

    if final_file:
        file_bytes = final_file.read()
        st.session_state.inv_image_bytes = file_bytes

    if st.session_state.inv_image_bytes:
        st.image(st.session_state.inv_image_bytes, caption="Factura cargada", width=350)

    btn_disabled = (not st.session_state.inv_image_bytes) or (selected_vendor_id is None)
    
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("💾 Guardar Borrador (Continuar luego)", disabled=btn_disabled, help="Guarda la foto y el proveedor para procesarlo más tarde."):
            save_draft()
            st.success("Borrador guardado. Puedes descargar el archivo desde el menú lateral si lo deseas.")
            
    with col_btn2:
        if st.button("🔍 Extraer Datos con IA", type="primary", disabled=btn_disabled):
            st.session_state.inv_vendor_id = selected_vendor_id
            st.session_state.inv_vendor_name = vendor_options[selected_vendor_id]
            
            try:
                with st.spinner("La IA (Gemini) está leyendo tu factura..."):
                    mime_type = final_file.type if final_file else "image/jpeg"
                    extracted = extract_invoice_data(st.session_state.inv_image_bytes, mime_type)
                    st.session_state.inv_extracted_data = extracted
                    st.session_state.inv_invoice_number = extracted.get("invoice_number") or ""
                    st.session_state.inv_invoice_date = extracted.get("invoice_date") or ""
                    
                    # Procesar líneas agregando reglas
                    raw_lines = extracted.get("line_items", [])
                    processed_lines = []
                    for line in raw_lines:
                        orig_desc = line.get("description", "")
                        qty = line.get("quantity", 1.0)
                        price = line.get("price_unit", 0.0)
                        sup_code = line.get("supplier_code") or ""
                        
                        # Buscar si hay regla previa
                        rule = find_matching_rule(selected_vendor_id, orig_desc)
                        applied_rule = False
                        applied_split_rule = None
                        if rule:
                            if rule.get("rule_type") == "split":
                                applied_rule = True
                                applied_split_rule = rule
                            else:
                                orig_qty = qty
                                qty = qty * rule["quantity_multiplier"]
                                # Si cambia cantidad, ajustamos proporcionalmente el precio unitario
                                if rule["quantity_multiplier"] != 0:
                                    price = price / rule["quantity_multiplier"]
                                applied_rule = True
                        
                        processed_lines.append({
                            "original_description": orig_desc,
                            "description": (rule["converted_description"] if rule and rule.get("rule_type") != "split" else orig_desc),
                            "quantity": float(qty),
                            "price_unit": float(price),
                            "supplier_code": sup_code,
                            "applied_rule": applied_rule,
                            "applied_split_rule": applied_split_rule,
                            "multiplier": (rule["quantity_multiplier"] if rule and rule.get("rule_type") != "split" else 1.0),
                            "odoo_product_id": (rule["odoo_product_id"] if rule and rule.get("rule_type") != "split" else None),
                            "odoo_default_code": (rule["odoo_default_code"] if rule and rule.get("rule_type") != "split" else "")
                        })
                    
                    st.session_state.inv_edited_lines = processed_lines
                    st.session_state.inv_step = 2
                    st.rerun()
            except Exception as e:
                st.error(f"❌ Error durante la extracción: {str(e)}")

def render_step_2():
    st.markdown("### Paso 2: Validación e ingreso de datos")
    st.write(f"**Proveedor seleccionado**: {st.session_state.inv_vendor_name}")
    
    col_num, col_date = st.columns([1, 1])
    with col_num:
        st.session_state.inv_invoice_number = st.text_input(
            "Número de Factura / Referencia:", 
            value=st.session_state.inv_invoice_number
        )
    with col_date:
        import datetime
        default_date = datetime.date.today()
        if st.session_state.inv_invoice_date:
            try:
                default_date = datetime.datetime.strptime(st.session_state.inv_invoice_date, "%Y-%m-%d").date()
            except ValueError:
                pass
        selected_date = st.date_input(
            "Fecha de la Factura:",
            value=default_date
        )
        st.session_state.inv_invoice_date = selected_date.strftime("%Y-%m-%d")

    st.markdown("#### 🎯 Margen y Redondeo Sugerido")
    col_margin, col_rounding = st.columns(2)
    with col_margin:
        suggested_margin = st.number_input(
            "Margen de ganancia sugerido por defecto (%):",
            min_value=0.0,
            max_value=500.0,
            value=float(st.session_state.get("inv_suggested_margin", 30.0)),
            step=5.0,
            help="Se utiliza para calcular el precio de venta sugerido (PVP) basado en el costo."
        )
        st.session_state.inv_suggested_margin = suggested_margin
        
    with col_rounding:
        rounding_options = ["none", "ceil_integer", "ceil_half"]
        rounding_labels = {
            "none": "Sin redondeo (exacto)",
            "ceil_integer": "Redondear al entero superior (ej. Q 12.15 -> Q 13.00)",
            "ceil_half": "Redondear a 0.50 superior (ej. Q 12.15 -> Q 12.50)"
        }
        
        selected_rounding = st.selectbox(
            "Método de redondeo de decimales:",
            options=rounding_options,
            format_func=lambda x: rounding_labels[x],
            index=rounding_options.index(st.session_state.get("inv_rounding_method", "ceil_integer")),
            help="Configura cómo promediar los decimales a la alta."
        )
        st.session_state.inv_rounding_method = selected_rounding

    # Preparar columnas para la conversión en la misma tabla
    for row in st.session_state.inv_edited_lines:
        if "unidades_paquete" not in row:
            row["unidades_paquete"] = 100.0
        if "aplicar_conversion" not in row:
            row["aplicar_conversion"] = False

    df_lines = pd.DataFrame(st.session_state.inv_edited_lines)
    if df_lines.empty:
        st.warning("No se extrajeron líneas. Agrega una nueva línea.")
        df_lines = pd.DataFrame(columns=["description", "quantity", "price_unit", "supplier_code", "unidades_paquete", "aplicar_conversion"])

    st.markdown("#### 🛠️ Edición y Conversión (Cientos, Libras)")
    st.info("💡 Edita las celdas directamente. Si compraste un paquete (ej. 1 ciento), escribe las unidades reales en 'Unds x Paquete' y marca '✅ Convertir'.")

    # Selector y editor de tabla
    edited_df = st.data_editor(
        df_lines[["description", "quantity", "price_unit", "supplier_code", "unidades_paquete", "aplicar_conversion"]],
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "description": st.column_config.TextColumn("Descripción (Odoo / Factura)", required=True),
            "quantity": st.column_config.NumberColumn("Cantidad", min_value=0.01, required=True, format="%.2f"),
            "price_unit": st.column_config.NumberColumn("Precio Unitario (Q)", min_value=0.0, required=True, format="Q %.4f"),
            "supplier_code": st.column_config.TextColumn("Cód. Prov."),
            "unidades_paquete": st.column_config.NumberColumn("Unds x Paquete", min_value=0.01, format="%.2f", help="Unidades reales del empaque/libra."),
            "aplicar_conversion": st.column_config.CheckboxColumn("✅ Convertir", default=False),
        }
    )

    # Procesar conversiones solicitadas desde la tabla
    needs_rerun = False
    new_lines = []
    for idx, row in edited_df.iterrows():
        orig_meta = st.session_state.inv_edited_lines[idx] if idx < len(st.session_state.inv_edited_lines) else {}
        line_data = {
            "original_description": orig_meta.get("original_description", row["description"]),
            "description": row["description"],
            "quantity": float(row["quantity"]),
            "price_unit": float(row["price_unit"]),
            "supplier_code": row["supplier_code"] if pd.notna(row["supplier_code"]) else "",
            "unidades_paquete": float(row.get("unidades_paquete", 100.0)),
            "aplicar_conversion": False, # Reset after applying
            "applied_rule": orig_meta.get("applied_rule", False),
            "multiplier": orig_meta.get("multiplier", 1.0),
            "odoo_product_id": orig_meta.get("odoo_product_id"),
            "odoo_default_code": orig_meta.get("odoo_default_code", "")
        }
        
        if row.get("aplicar_conversion", False):
            factor = line_data["unidades_paquete"]
            line_data["quantity"] *= factor
            line_data["price_unit"] /= factor
            needs_rerun = True
            
        new_lines.append(line_data)
        
    st.session_state.inv_edited_lines = new_lines
    if needs_rerun:
        st.rerun()

    # Botones de navegación
    col_prev, col_next = st.columns([1, 1])
    with col_prev:
        if st.button("← Volver a cargar"):
            st.session_state.inv_step = 1
            st.rerun()
    with col_next:
        if st.button("Buscar en Odoo →", type="primary"):
            # Actualizar el session state con los datos modificados del data_editor
            new_lines = []
            for idx, row in edited_df.iterrows():
                # Conservar metadata original si existía en ese índice
                orig_meta = st.session_state.inv_edited_lines[idx] if idx < len(st.session_state.inv_edited_lines) else {}
                new_lines.append({
                    "original_description": orig_meta.get("original_description", row["description"]),
                    "description": row["description"],
                    "quantity": float(row["quantity"]),
                    "price_unit": float(row["price_unit"]),
                    "supplier_code": row["supplier_code"] if pd.notna(row["supplier_code"]) else "",
                    "applied_rule": orig_meta.get("applied_rule", False),
                    "multiplier": orig_meta.get("multiplier", 1.0),
                    "odoo_product_id": orig_meta.get("odoo_product_id"),
                    "odoo_default_code": orig_meta.get("odoo_default_code", "")
                })
            st.session_state.inv_edited_lines = new_lines
            st.session_state.inv_step = 3
            save_draft()
            st.rerun()

def render_step_3(client: OdooRPC):
    st.markdown("### Paso 3: Vinculación de Productos en Odoo")
    st.write("Verificando si los ítems existen en el catálogo de tu Odoo...")

    # Realizar matching: Conservar los ya vinculados por descripción
    existing_matches = {m["line_desc"]: m for m in st.session_state.inv_product_matches}
    new_matches = []
    
    with st.spinner("Buscando coincidencias en Odoo y recuperando previos..."):
        for line in st.session_state.inv_edited_lines:
            desc = line["description"]
            if desc in existing_matches:
                new_matches.append(existing_matches[desc])
                continue
                
            # Caso 0: Regla de tipo split pre-asociada
            if line.get("applied_split_rule"):
                split_rule = line["applied_split_rule"]
                new_matches.append({
                    "line_desc": desc,
                    "found": True,
                    "action": "split_item",
                    "match_origin": "rule",
                    "split_products": [
                        {
                            "product_id": sp["odoo_product_id"],
                            "odoo_name": sp["odoo_name"],
                            "default_code": sp["odoo_default_code"],
                            "quantity_multiplier": sp["quantity_multiplier"],
                            "cost_share": sp["cost_share"]
                        }
                        for sp in split_rule["split_products"]
                    ]
                })
                continue

            match = None
            match_origin = "search"
            
            # 1. Si ya tiene un id pre-asociado por regla (historial), buscar detalles directos
            if line.get("odoo_product_id"):
                try:
                    match = client.get_product_details(line["odoo_product_id"])
                    if match:
                        match_origin = "rule"
                except Exception:
                    pass
            
            # 2. Si no hay match por regla, y la línea tiene supplier_code, buscar por código de proveedor/fabricante
            supplier_code = line.get("supplier_code")
            if not match and supplier_code:
                try:
                    match = client.find_product_by_code(supplier_code, st.session_state.inv_vendor_id)
                    if match:
                        match_origin = "code"
                except Exception:
                    pass
            
            # 3. De lo contrario, buscar por descripción
            if not match:
                match = client.search_product(desc, st.session_state.inv_vendor_id)
                if match:
                    if supplier_code and match.get("default_code") == supplier_code:
                        match_origin = "code"
                    else:
                        match_origin = "search"

            if match:
                new_matches.append({
                    "line_desc": desc,
                    "found": True,
                    "product_id": match["id"],
                    "odoo_name": match["name"],
                    "uom_id": match["uom_id"],
                    "default_code": match.get("default_code") or "",
                    "action": "use_existing",
                    "match_origin": match_origin
                })
            else:
                new_matches.append({
                    "line_desc": desc,
                    "found": False,
                    "product_id": None,
                    "odoo_name": "",
                    "uom_id": 1, # UoM Unidad por defecto
                    "default_code": supplier_code or "",
                    "action": "create_new",
                    "match_origin": "none"
                })
                
    st.session_state.inv_product_matches = new_matches

    # Mostrar preview y permitir modificaciones
    st.markdown("#### Coincidencias encontradas")
    
    @st.fragment
    def render_match_item(i: int, match: dict, line: dict, client):
            col_desc, col_match, col_action = st.columns([2, 2, 1])
        
            with col_desc:
                st.write(f"**Línea**: `{line['description']}` (Cant: {line['quantity']} | Unit: Q {line['price_unit']:.2f})")
            
            with col_match:
                if match["found"] and match.get("action", "use_existing") == "use_existing":
                    origin = match.get("match_origin", "search")
                    if origin == "code":
                        tag = "🟢 [CÓDIGO]"
                    elif origin == "rule":
                        tag = "🧠 [HISTORIAL]"
                    else:
                        tag = "🔍 [BÚSQUEDA]"
                    st.success(f"{tag} Odoo Match: **[{match['default_code']}] {match['odoo_name']}**")
                elif match.get("action") == "map_existing" and match.get("manually_mapped"):
                    st.info(f"🔗 Vinculado a: **[{match['default_code']}] {match['odoo_name']}**")
                else:
                    st.warning("⚠️ No se encontró coincidencia en Odoo.")
                
            with col_action:
                action_options = ["use_existing", "create_new", "map_existing", "split_item", "ignore"]
                action_labels = {
                    "use_existing": "Usar Match Sugerido",
                    "create_new": "Crear Nuevo",
                    "map_existing": "Buscar Catálogo",
                    "split_item": "Descomponer Línea",
                    "ignore": "Ignorar / Eliminar Línea"
                }
            
                if not match["found"]:
                    action_options.remove("use_existing")
            
                # Determinar el índice por defecto según el estado actual de match["action"]
                current_action = match.get("action")
                if current_action not in action_options:
                    current_action = action_options[0]
                    match["action"] = current_action
                
                idx_default = action_options.index(current_action)
                
                selected_action = st.selectbox(
                    "Acción:",
                    options=action_options,
                    format_func=lambda x: action_labels[x],
                    index=idx_default,
                    key=f"act_{i}"
                )
                match["action"] = selected_action

            if selected_action == "create_new":
                has_creations = True
                # Configurar datos del nuevo producto
                col_empty, col_new_name, col_new_code = st.columns([0.5, 2.5, 2])
                with col_new_name:
                    match["new_name"] = st.text_input(
                        "Nombre en Odoo:", 
                        value=match.get("new_name") or match["odoo_name"] or match["line_desc"], 
                        key=f"new_name_{i}"
                    )
                with col_new_code:
                    match["new_code"] = st.text_input(
                        "Código Interno / Ref:", 
                        value=match.get("new_code") or match["default_code"], 
                        key=f"new_code_{i}"
                    )
            elif selected_action == "map_existing":
                # Autocompletado del catálogo
                products = st.session_state.inv_odoo_products
                def get_prod_label(p):
                    code = p.get("default_code")
                    if code:
                        return f"{p['name']} [{code}]"
                    return p['name']
            
                col_empty, col_search_prod = st.columns([0.5, 4.5])
                with col_search_prod:
                    # Buscar índice del producto ya seleccionado si existe y fue mapeado manualmente
                    current_id = match.get("product_id")
                    default_idx = None
                    if current_id and match.get("manually_mapped"):
                        for idx, p in enumerate(products):
                            if p["id"] == current_id:
                                default_idx = idx
                                break
                            
                    selected_p = st.selectbox(
                        "Selecciona el producto existente de Odoo:",
                        options=products,
                        format_func=get_prod_label,
                        index=default_idx,
                        placeholder="Escribe para buscar...",
                        key=f"map_p_{i}"
                    )
                    if selected_p:
                        match["product_id"] = selected_p["id"]
                        match["odoo_name"] = selected_p["name"]
                        match["default_code"] = selected_p.get("default_code") or ""
                        match["manually_mapped"] = True
            elif selected_action == "split_item":
                if "split_products" not in match or not match["split_products"]:
                    match["split_products"] = [
                        {"product_id": None, "odoo_name": "", "default_code": "", "quantity_multiplier": 1.0, "cost_share": 0.5, "action": "map_existing"},
                        {"product_id": None, "odoo_name": "", "default_code": "", "quantity_multiplier": 1.0, "cost_share": 0.5, "action": "map_existing"}
                    ]
                
                products = st.session_state.inv_odoo_products
                def get_prod_label(p):
                    code = p.get("default_code")
                    if code:
                        return f"{p['name']} [{code}]"
                    return p['name']

                col_empty_n, col_num_splits = st.columns([0.5, 4.5])
                with col_num_splits:
                    num_splits = st.number_input(
                        "Dividir en n productos:",
                        min_value=2,
                        max_value=5,
                        value=len(match["split_products"]),
                        step=1,
                        key=f"num_splits_{i}"
                    )
                
                if num_splits != len(match["split_products"]):
                    if num_splits > len(match["split_products"]):
                        for _ in range(num_splits - len(match["split_products"])):
                            match["split_products"].append({"product_id": None, "odoo_name": "", "default_code": "", "quantity_multiplier": 1.0, "cost_share": 1.0 / num_splits, "action": "map_existing"})
                    else:
                        match["split_products"] = match["split_products"][:num_splits]
                
                total_percentage = 0.0
                for j, sp in enumerate(match["split_products"]):
                    st.markdown(f"   ↳ **Sub-producto #{j+1}**")
                    
                    # 1. Selector de Acción para este sub-producto
                    col_empty_act, col_action_sub = st.columns([0.5, 4.5])
                    with col_action_sub:
                        sub_action_options = ["map_existing", "create_new"]
                        sub_action_labels = {
                            "map_existing": "Vincular a producto existente de Odoo",
                            "create_new": "Crear nuevo producto en Odoo"
                        }
                        sp_action = sp.get("action", "map_existing")
                        if sp_action not in sub_action_options:
                            sp_action = "map_existing"
                            
                        selected_sp_action = st.selectbox(
                            f"Acción para Sub-producto #{j+1}:",
                            options=sub_action_options,
                            format_func=lambda x: sub_action_labels[x],
                            index=sub_action_options.index(sp_action),
                            key=f"split_act_{i}_{j}"
                        )
                        sp["action"] = selected_sp_action
                    
                    # 2. Renderizar campos según la acción seleccionada
                    col_empty, col_col1, col_col2, col_col3 = st.columns([0.5, 2.5, 1, 1])
                    
                    if selected_sp_action == "create_new":
                        with col_col1:
                            sp["new_name"] = st.text_input(
                                "Nombre en Odoo:",
                                value=sp.get("new_name") or sp.get("odoo_name") or f"{line['description']} - Parte {j+1}",
                                key=f"split_new_name_{i}_{j}"
                            )
                        with col_col2:
                            sp["new_code"] = st.text_input(
                                "Ref Interna:",
                                value=sp.get("new_code") or sp.get("default_code") or "",
                                key=f"split_new_code_{i}_{j}"
                            )
                        with col_col3:
                            qty_factura = line["quantity"]
                            price_factura = line["price_unit"]
                            mult = sp.get("quantity_multiplier", 1.0)
                            share = sp.get("cost_share", 0.5)
                            sub_cost = (price_factura * share) / mult if mult != 0 else 0.0
                            
                            suggested_sale = sp.get("new_sale_price") if sp.get("new_sale_price") is not None else calculate_suggested_pvp(sub_cost)
                            sp["new_sale_price"] = st.number_input(
                                "PVP sugerido (Q):",
                                min_value=0.0,
                                value=float(suggested_sale),
                                step=0.5,
                                key=f"split_new_sale_{i}_{j}"
                            )
                            
                        col_empty2, col_mult_c, col_share_c = st.columns([0.5, 2.25, 2.25])
                        with col_mult_c:
                            sp["quantity_multiplier"] = st.number_input(
                                "Mult. Cantidad:",
                                min_value=0.01,
                                value=float(sp.get("quantity_multiplier", 1.0)),
                                step=1.0,
                                key=f"split_mult_{i}_{j}"
                            )
                        with col_share_c:
                            percentage = st.number_input(
                                "% Costo:",
                                min_value=0.0,
                                max_value=100.0,
                                value=float(sp.get("cost_share", 0.5) * 100.0),
                                step=5.0,
                                key=f"split_share_{i}_{j}"
                            )
                            sp["cost_share"] = percentage / 100.0
                            total_percentage += percentage
                    else: # map_existing
                        with col_col1:
                            default_idx = None
                            if sp.get("product_id"):
                                for idx, p in enumerate(products):
                                    if p["id"] == sp["product_id"]:
                                        default_idx = idx
                                        break
                            
                            selected_p = st.selectbox(
                                f"Producto Odoo:",
                                options=products,
                                format_func=get_prod_label,
                                index=default_idx,
                                placeholder="Escribe para buscar...",
                                key=f"split_p_{i}_{j}"
                            )
                            if selected_p:
                                sp["product_id"] = selected_p["id"]
                                sp["odoo_name"] = selected_p["name"]
                                sp["default_code"] = selected_p.get("default_code") or ""
                                if "list_price" not in sp or sp.get("product_id") != selected_p["id"]:
                                    sp["list_price"] = selected_p.get("list_price", 0.0)
                        
                        with col_col2:
                            sp["quantity_multiplier"] = st.number_input(
                                "Mult. Cantidad:",
                                min_value=0.01,
                                value=float(sp.get("quantity_multiplier", 1.0)),
                                step=1.0,
                                key=f"split_mult_{i}_{j}"
                            )
                        
                        with col_col3:
                            percentage = st.number_input(
                                "% Costo:",
                                min_value=0.0,
                                max_value=100.0,
                                value=float(sp.get("cost_share", 0.5) * 100.0),
                                step=5.0,
                                key=f"split_share_{i}_{j}"
                            )
                            sp["cost_share"] = percentage / 100.0
                            total_percentage += percentage

                        if sp.get("product_id"):
                            if "list_price" not in sp:
                                sp["list_price"] = 0.0
                            qty_factura = line["quantity"]
                            price_factura = line["price_unit"]
                            mult = sp.get("quantity_multiplier", 1.0)
                            share = sp.get("cost_share", 0.5)
                            sub_cost = (price_factura * share) / mult if mult != 0 else 0.0
                            
                            col_empty2, col_prices_info, col_checkbox_upd = st.columns([0.5, 2.5, 2])
                            with col_prices_info:
                                st.markdown(f"💵 Venta actual: **Q {sp['list_price']:.2f}** | Compra: **Q {sub_cost:.2f}**")
                            with col_checkbox_upd:
                                update_price = st.checkbox(
                                    "Actualizar PVP",
                                    key=f"split_upd_pr_{i}_{j}",
                                    value=sp.get("update_sale_price", False)
                                )
                                sp["update_sale_price"] = update_price
                            
                            if update_price:
                                col_empty3, col_price_input = st.columns([0.5, 4.5])
                                with col_price_input:
                                    suggested_price = sp.get("new_sale_price") if sp.get("new_sale_price") is not None else sp["list_price"]
                                    sp["new_sale_price"] = st.number_input(
                                        "Nuevo PVP (Q):",
                                        min_value=0.0,
                                        value=float(suggested_price),
                                        step=0.5,
                                        key=f"split_new_val_{i}_{j}"
                                    )

                col_empty_err, col_status_msg = st.columns([0.5, 4.5])
                with col_status_msg:
                    if abs(total_percentage - 100.0) > 0.01:
                        st.error(f"⚠️ La suma de porcentajes de costo debe ser 100% (Suma actual: {total_percentage:.1f}%)")
                    else:
                        st.success("✅ Distribución del costo válida (100%).")

            # Gestionar precios de venta (PVP)
            if selected_action in ["use_existing", "map_existing"] and match.get("product_id"):
                if "list_price" not in match:
                    cached = next((p for p in st.session_state.inv_odoo_products if p["id"] == match["product_id"]), None)
                    if cached:
                        match["list_price"] = cached.get("list_price", 0.0)
                    else:
                        try:
                            details = client.get_product_details(match["product_id"])
                            match["list_price"] = details.get("list_price", 0.0)
                        except Exception:
                            match["list_price"] = 0.0

                col_empty_p, col_prices_info, col_checkbox_upd = st.columns([0.5, 2.5, 2])
                with col_prices_info:
                    st.markdown(f"💵 Venta actual: **Q {match['list_price']:.2f}** | Compra: **Q {line['price_unit']:.2f}**")
                with col_checkbox_upd:
                    update_price = st.checkbox("Actualizar PVP en Odoo", key=f"upd_pr_{i}", value=match.get("update_sale_price", False))
                    match["update_sale_price"] = update_price

                if update_price:
                    col_empty_p2, col_price_input = st.columns([0.5, 4.5])
                    with col_price_input:
                        suggested_price = match.get("new_sale_price") if match.get("new_sale_price") is not None else match["list_price"]
                        new_sale_p = st.number_input(
                            "Nuevo precio de venta al público (Q):",
                            min_value=0.0,
                            value=float(suggested_price),
                            step=0.5,
                            key=f"new_val_{i}"
                        )
                        match["new_sale_price"] = new_sale_p

            elif selected_action == "create_new":
                col_empty_p, col_new_sale_p = st.columns([0.5, 4.5])
                with col_new_sale_p:
                    suggested_sale = match.get("new_sale_price") if match.get("new_sale_price") is not None else calculate_suggested_pvp(line["price_unit"])
                    new_sale_p = st.number_input(
                        "Precio de venta al público sugerido (Q):",
                        min_value=0.0,
                        value=float(suggested_sale),
                        step=0.5,
                        key=f"new_val_create_{i}"
                    )
                    match["new_sale_price"] = new_sale_p

            if selected_action != "ignore":
                col_empty_b, col_bulk = st.columns([0.5, 4.5])
                with col_bulk:
                    update_bulk = st.checkbox("💰 Actualizar Descuento por Volumen (Lista de Precios)", key=f"upd_bulk_{i}", value=match.get("update_bulk_price", False))
                    match["update_bulk_price"] = update_bulk
                    if update_bulk:
                        col_bq, col_bp = st.columns(2)
                        with col_bq:
                            bulk_q = st.number_input("Cant. Mínima (ej. 100):", min_value=1.0, value=float(match.get("bulk_quantity", 100.0)), step=1.0, key=f"bq_{i}")
                            match["bulk_quantity"] = bulk_q
                        with col_bp:
                            bulk_p = st.number_input(f"Precio Total a cobrar por {int(bulk_q)}:", min_value=0.01, value=float(match.get("bulk_price", calculate_suggested_pvp(line["price_unit"]) * bulk_q)), step=0.5, key=f"bp_{i}")
                            match["bulk_price"] = bulk_p

            save_draft()
            st.markdown("---")


    has_creations = any(m.get("action") == "create_new" for m in st.session_state.inv_product_matches)
    for i, match in enumerate(st.session_state.inv_product_matches):
        line = st.session_state.inv_edited_lines[i]
        render_match_item(i, match, line, client)

    # Botones
    col_prev, col_next = st.columns([1, 1])
    with col_prev:
        if st.button("← Atrás"):
            st.session_state.inv_step = 2
            save_draft()
            st.rerun()
            
    with col_next:
        confirm_text = "Confirmar y Crear PO" if not has_creations else "Crear Productos Nuevos y PO"
        if st.button(confirm_text, type="primary"):
            st.session_state.inv_step = 4
            save_draft()
            st.rerun()

    # Autoguardar cada vez que se interactúe con la tabla de vinculaciones
    save_draft()

def render_step_4(client: OdooRPC):
    st.markdown("### Paso 4: Creando Registros en Odoo...")
    
    if st.session_state.inv_creating_po:
        st.warning("Ya hay una creación en curso. Espere un momento.")
        return

    st.session_state.inv_creating_po = True

    try:
        po_lines = []
        rules_to_save = []

        # Obtener primer impuesto (IVA 12% por defecto)
        default_tax_ids = [st.session_state.inv_odoo_taxes[0]['id']] if st.session_state.inv_odoo_taxes else []

        for i, match in enumerate(st.session_state.inv_product_matches):
            line = st.session_state.inv_edited_lines[i]
            
            if match.get("action") == "ignore":
                continue
                
            if match.get("action") == "split_item":
                # Agregar sub-líneas a la PO
                for sp in match["split_products"]:
                    qty_factura = line["quantity"]
                    price_factura = line["price_unit"]
                    mult = sp["quantity_multiplier"]
                    share = sp["cost_share"]
                    
                    sub_qty = qty_factura * mult
                    sub_price = (price_factura * share) / mult if mult != 0 else 0.0
                    
                    product_id = sp.get("product_id")
                    
                    # A. Si se seleccionó crear nuevo subproducto
                    if sp.get("action") == "create_new":
                        with st.spinner(f"Creando sub-producto '{sp['new_name']}' en Odoo..."):
                            product_id = client.create_product(
                                name=sp["new_name"],
                                default_code=sp["new_code"],
                                type='consu',
                                purchase_tax_ids=default_tax_ids,
                                vendor_id=st.session_state.inv_vendor_id,
                                vendor_price=sub_price,
                                vendor_code=sp["new_code"],
                                sale_price=sp.get("new_sale_price")
                            )
                            # Actualizar datos en sp para que se guarden en la regla
                            sp["product_id"] = product_id
                            sp["odoo_name"] = sp["new_name"]
                            sp["default_code"] = sp["new_code"]
                            
                            # Crear regla de reabastecimiento min/max
                            try:
                                client.create_reordering_rule(product_id, 1.0 if sub_qty > 1.0 else 0.0, float(sub_qty) if sub_qty > 1.0 else 1.0)
                            except Exception as re_err:
                                st.warning(f"⚠️ No se pudo crear la regla de reabastecimiento para '{sp['new_name']}': {str(re_err)}")
                                
                    # B. Si es existente y requiere actualizar PVP
                    elif sp.get("action") == "map_existing" and sp.get("update_sale_price") and sp.get("new_sale_price") is not None:
                        with st.spinner(f"Actualizando PVP del sub-producto '{sp['odoo_name']}'..."):
                            try:
                                client.update_product_sale_price(product_id, sp["new_sale_price"])
                            except Exception as e:
                                st.warning(f"⚠️ No se pudo actualizar el PVP para '{sp['odoo_name']}': {str(e)}")

                    po_lines.append({
                        'product_id': product_id,
                        'name': sp["odoo_name"],
                        'product_qty': float(sub_qty),
                        'price_unit': float(sub_price),
                        'product_uom': 1, # Unidad por defecto
                        'taxes_id': default_tax_ids
                    })
                
                # Guardar regla de split
                rules_to_save.append({
                    "rule_type": "split",
                    "vendor_id": st.session_state.inv_vendor_id,
                    "vendor_name": st.session_state.inv_vendor_name,
                    "original_description": line["original_description"],
                    "split_products": match["split_products"]
                })
                continue
                
            product_id = match["product_id"]

            # 1. Crear producto si se seleccionó "create_new"
            if match["action"] == "create_new":
                with st.spinner(f"Creando producto '{match['new_name']}' en Odoo..."):
                    product_id = client.create_product(
                        name=match["new_name"],
                        default_code=match["new_code"],
                        type='consu',
                        purchase_tax_ids=default_tax_ids,
                        vendor_id=st.session_state.inv_vendor_id,
                        vendor_price=line["price_unit"],
                        vendor_code=match["new_code"],
                        sale_price=match.get("new_sale_price")
                    )
                    
                    # Generar regla automática para guardar al final
                    rules_to_save.append({
                        "vendor_id": st.session_state.inv_vendor_id,
                        "vendor_name": st.session_state.inv_vendor_name,
                        "original_description": line["original_description"],
                        "converted_description": match["new_name"],
                        "quantity_multiplier": 1.0,
                        "odoo_product_id": product_id,
                        "odoo_default_code": match["new_code"]
                    })
                    
                    # Crear regla de reabastecimiento (min/max)
                    qty_bought = line["quantity"]
                    min_q = 1.0 if qty_bought > 1.0 else 0.0
                    max_q = float(qty_bought) if qty_bought > 1.0 else 1.0
                    try:
                        client.create_reordering_rule(product_id, min_q, max_q)
                    except Exception as re_err:
                        st.warning(f"⚠️ No se pudo crear la regla de reabastecimiento para '{match['new_name']}': {str(re_err)}")
            elif match["action"] == "map_existing" or (match["action"] == "use_existing" and match.get("manually_mapped")):
                # Guardar regla de mapeo manual para el producto existente
                rules_to_save.append({
                    "vendor_id": st.session_state.inv_vendor_id,
                    "vendor_name": st.session_state.inv_vendor_name,
                    "original_description": line["original_description"],
                    "converted_description": match["odoo_name"],
                    "quantity_multiplier": 1.0,
                    "odoo_product_id": product_id,
                    "odoo_default_code": match["default_code"]
                })

            # 2. Actualizar precio de venta si se solicitó (para productos existentes)
            if match.get("action") in ["use_existing", "map_existing"] and match.get("update_sale_price") and match.get("new_sale_price") is not None:
                with st.spinner(f"Actualizando precio de venta de '{match['odoo_name']}' en Odoo..."):
                    try:
                        client.update_product_sale_price(product_id, match["new_sale_price"])
                    except Exception as e:
                        st.warning(f"⚠️ No se pudo actualizar el precio de venta para '{match['odoo_name']}': {str(e)}")

            # 3. Actualizar descuento por volumen (Pricelist) si se solicitó
            if match.get("update_bulk_price") and match.get("bulk_quantity") and match.get("bulk_price"):
                with st.spinner(f"Configurando descuento por volumen para '{match.get('odoo_name', match.get('new_name', ''))}'..."):
                    try:
                        # Si es existente, hay que obtener el product_tmpl_id para la lista de precios
                        tmpl_id = None
                        if match.get("action") == "create_new":
                            # Cuando se crea, get_product_details puede traernos el tmpl_id
                            details = client.get_product_details(product_id)
                            tmpl_id = details.get("product_tmpl_id")
                        else:
                            # Puede venir en el match o lo buscamos
                            tmpl_id = match.get("product_tmpl_id")
                            if not tmpl_id:
                                details = client.get_product_details(product_id)
                                tmpl_id = details.get("product_tmpl_id")
                                
                        if tmpl_id:
                            qty = float(match["bulk_quantity"])
                            total_price = float(match["bulk_price"])
                            unit_price = total_price / qty
                            client.update_product_pricelist_item(tmpl_id, qty, unit_price)
                    except Exception as e:
                        st.warning(f"⚠️ No se pudo actualizar el precio por volumen: {str(e)}")
            
            # Obtener uom_id (vía lectura si existía)
            uom_id = match.get("uom_id")
            if match["action"] == "use_existing" and not uom_id:
                details = client.get_product_details(product_id)
                uom_id = details["uom_id"]
            elif not uom_id:
                # Default a UoM unidad (id 1)
                uom_id = 1

            po_lines.append({
                'product_id': product_id,
                'name': match["new_name"] if match["action"] == "create_new" else match["odoo_name"],
                'product_qty': line["quantity"],
                'price_unit': line["price_unit"],
                'product_uom': uom_id,
                'taxes_id': default_tax_ids
            })

        # 2. Crear Orden de Compra
        if not po_lines:
            raise Exception("No hay líneas válidas para procesar. Todas las líneas fueron descartadas o ignoradas.")
            
        with st.spinner("Creando Orden de Compra (RFQ) en Odoo..."):
            po_result = client.create_purchase_order(
                vendor_id=st.session_state.inv_vendor_id,
                lines=po_lines
            )
            st.session_state.inv_po_result = po_result
            st.session_state.inv_rules_to_save = rules_to_save
            
            # Guardar reglas locales
            for r in rules_to_save:
                if r.get("rule_type") == "split":
                    from modules.rules_matrix import create_or_update_split_rule
                    create_or_update_split_rule(
                        vendor_id=r["vendor_id"],
                        vendor_name=r["vendor_name"],
                        original_description=r["original_description"],
                        split_products=r["split_products"]
                    )
                else:
                    create_or_update_rule(
                        vendor_id=r["vendor_id"],
                        vendor_name=r["vendor_name"],
                        original_description=r["original_description"],
                        converted_description=r["converted_description"],
                        quantity_multiplier=r["quantity_multiplier"],
                        odoo_product_id=r["odoo_product_id"],
                        odoo_default_code=r["odoo_default_code"]
                    )

        st.session_state.inv_step = 5
        st.session_state.inv_creating_po = False
        clear_draft()
        st.rerun()

    except Exception as e:
        st.session_state.inv_creating_po = False
        st.error(f"❌ Error al procesar en Odoo: {str(e)}")
        if st.button("Volver al paso anterior"):
            st.session_state.inv_step = 3
            st.rerun()

def render_step_5(client: OdooRPC):
    st.markdown("### ¡Orden de Compra Creada Correctamente! 🎉")
    
    result = st.session_state.inv_po_result
    if not result:
        st.warning("No hay datos de la Orden de Compra.")
        if st.button("📸 Procesar nueva factura", type="primary"):
            reset_flow()
            st.rerun()
        return

    st.markdown(f"**Referencia Odoo**: `{result['name']}`")
    st.markdown(f"**Monto Total**: `Q {result['amount_total']:.2f}`")
    
    odoo_url = os.getenv("ODOO_URL")
    web_link = f"{odoo_url}/web#id={result['id']}&model=purchase.order&view_type=form"
    st.markdown(f"[🔗 Abrir en Odoo]({web_link})")
    
    st.markdown("---")
    st.subheader("⚙️ Automatización del Flujo de Compra en Odoo")
    st.write("Completa el flujo contable y de inventario de esta compra en Odoo desde aquí:")

    # Paso 1: Confirmar PO
    col_p1_text, col_p1_btn = st.columns([3, 1])
    with col_p1_text:
        st.write("**Paso 1: Confirmar Orden de Compra**")
        if st.session_state.inv_po_confirmed:
            st.success("✔️ Orden confirmada en Odoo.")
        else:
            st.info("La orden está en borrador (RFQ).")
    with col_p1_btn:
        confirm_btn = st.button("Confirmar PO", disabled=st.session_state.inv_po_confirmed, use_container_width=True)
        if confirm_btn:
            with st.spinner("Confirmando orden en Odoo..."):
                try:
                    client.confirm_purchase_order(result['id'])
                    st.session_state.inv_po_confirmed = True
                    st.success("¡Orden confirmada!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al confirmar PO: {str(e)}")

    # Paso 2: Recibir mercadería
    col_p2_text, col_p2_btn = st.columns([3, 1])
    with col_p2_text:
        st.write("**Paso 2: Recibir Mercadería en Inventario**")
        if st.session_state.inv_picking_validated:
            st.success("✔️ Recepción validada al 100% en Odoo.")
        else:
            st.info("Espera la confirmación de la orden.")
    with col_p2_btn:
        receive_btn = st.button("Recibir Insumos", disabled=(not st.session_state.inv_po_confirmed or st.session_state.inv_picking_validated), use_container_width=True)
        if receive_btn:
            with st.spinner("Registrando entrada de mercadería..."):
                try:
                    client.validate_incoming_picking(result['id'])
                    st.session_state.inv_picking_validated = True
                    st.success("¡Inventario recibido!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al recibir inventario: {str(e)}")

    # Paso 3: Crear Factura
    st.write("**Paso 3: Crear y Publicar Factura de Proveedor (Bill)**")
    if st.session_state.inv_bill_id:
        st.success(f"✔️ Factura contable creada y publicada en Odoo.")
        bill_link = f"{odoo_url}/web#id={st.session_state.inv_bill_id}&model=account.move&view_type=form"
        st.markdown(f"[🔗 Ver Factura en Odoo]({bill_link})")
    else:
        # Configurar vencimiento
        col_term, col_bill_btn = st.columns([3, 1])
        with col_term:
            plazo_pago = st.selectbox(
                "Plazo de pago para vencimiento:",
                options=["Contado", "30 días", "45 días", "60 días"],
                key="plazo_pago_odoo"
            )
            
            # Calcular fecha de vencimiento
            try:
                inv_date = datetime.datetime.strptime(st.session_state.inv_invoice_date, "%Y-%m-%d").date()
            except ValueError:
                inv_date = datetime.date.today()
                
            if plazo_pago == "30 días":
                due_date = inv_date + datetime.timedelta(days=30)
            elif plazo_pago == "45 días":
                due_date = inv_date + datetime.timedelta(days=45)
            elif plazo_pago == "60 días":
                due_date = inv_date + datetime.timedelta(days=60)
            else:
                due_date = inv_date
                
            st.caption(f"Fecha factura: **{inv_date}** | Vencimiento calculado: **{due_date}**")
            
        with col_bill_btn:
            st.write("")  # alineación
            st.write("")
            bill_btn = st.button("Crear Factura", disabled=(not st.session_state.inv_picking_validated), use_container_width=True)
            if bill_btn:
                with st.spinner("Creando y publicando factura en Odoo..."):
                    try:
                        bill_id = client.create_and_post_vendor_bill(
                            po_id=result['id'],
                            invoice_date=st.session_state.inv_invoice_date,
                            due_date=due_date.strftime("%Y-%m-%d"),
                            invoice_ref=st.session_state.inv_invoice_number
                        )
                        st.session_state.inv_bill_id = bill_id
                        st.session_state.inv_bill_posted = True
                        st.session_state.inv_payment_term = plazo_pago
                        register_processed_bill_id(bill_id)
                        st.success("¡Factura publicada con éxito!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error al facturar: {str(e)}")

    # Paso 4: Registrar Pago
    term_selected = st.session_state.get("inv_payment_term", "Contado")
    if term_selected == "Contado":
        st.write("**Paso 4: Registrar Pago Contable (Opcional)**")
        if st.session_state.inv_payment_registered:
            st.success("✔️ Pago registrado y asentado en Odoo.")
        else:
            # Cargar diarios
            if "inv_odoo_journals" not in st.session_state or not st.session_state.inv_odoo_journals:
                try:
                    st.session_state.inv_odoo_journals = client.fetch_payment_journals()
                except Exception:
                    st.session_state.inv_odoo_journals = []
                    
            if st.session_state.inv_odoo_journals:
                col_journal, col_pay_date, col_pay_btn = st.columns([2, 1.5, 1.5])
                with col_journal:
                    journal_options = {j['id']: f"{j['name']} ({j['code']})" for j in st.session_state.inv_odoo_journals}
                    selected_journal_id = st.selectbox(
                        "Diario de Pago:",
                        options=list(journal_options.keys()),
                        format_func=lambda x: journal_options[x],
                        key="journal_pago_odoo"
                    )
                with col_pay_date:
                    pay_date_val = st.date_input("Fecha de Pago:", value=datetime.date.today())
                with col_pay_btn:
                    st.write("")
                    st.write("")
                    pay_btn = st.button("Registrar Pago", disabled=(not st.session_state.inv_bill_posted), use_container_width=True)
                    if pay_btn:
                        with st.spinner("Asentando pago en Odoo..."):
                            try:
                                client.register_bill_payment(
                                    bill_id=st.session_state.inv_bill_id,
                                    journal_id=selected_journal_id,
                                    payment_date=pay_date_val.strftime("%Y-%m-%d")
                                )
                                st.session_state.inv_payment_registered = True
                                st.success("¡Pago registrado!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error al registrar pago: {str(e)}")
            else:
                st.info("No se pudieron cargar diarios de pago activos (Banco/Caja) en Odoo.")
    else:
        st.info(f"ℹ️ Factura registrada a Crédito ({term_selected}). Puedes consultar y pagar esta factura en la pestaña **Cuentas por Pagar (Odoo)**.")

    # Registro en Semáforo local
    st.write("---")
    try:
        inv_date = datetime.datetime.strptime(st.session_state.inv_invoice_date, "%Y-%m-%d").date()
    except Exception:
        inv_date = datetime.date.today()
        
    is_before_today = inv_date < datetime.date(2026, 6, 24)
    
    if is_before_today:
        st.info("ℹ️ Esta factura tiene una fecha anterior a hoy. Se asume que ya está registrada en el Semáforo local (Google Sheet), por lo que solo se procesará en Odoo.")
    else:
        st.markdown("#### ¿Registrar en el presupuesto local de FerreCheck?")
        
        # Mapear la modalidad seleccionada en Odoo al formato local
        term_selected = st.session_state.get("inv_payment_term", "Contado")
        if term_selected == "Contado":
            modalidad_local = "Contado"
        else:
            modalidad_local = f"Crédito {term_selected}"
            
        st.write(f"Agrega el total de esta compra a tu Semáforo de compras local Emmanuel bajo la modalidad **{modalidad_local}** (según tu selección para Odoo).")
        
        if st.button("📥 Registrar localmente", type="secondary", use_container_width=True):
            if "periodo_actual" in st.session_state:
                p = st.session_state.periodo_actual
                import uuid
                nueva_compra = {
                    "id": str(uuid.uuid4()),
                    "monto": float(result['amount_total']),
                    "proveedor": st.session_state.inv_vendor_name,
                    "fecha": st.session_state.inv_invoice_date if st.session_state.inv_invoice_date else datetime.date.today().strftime("%Y-%m-%d"),
                    "nota": f"Importado de Odoo PO {result['name']} | Fac: {st.session_state.inv_invoice_number}",
                    "modalidad": modalidad_local
                }
                p["compras"].append(nueva_compra)
                
                from modules.sheets import is_sheets_active, sync_all_purchases_to_sheets
                if is_sheets_active():
                    with st.spinner("Sincronizando compra con Google Sheets..."):
                        sync_all_purchases_to_sheets(p["compras"], p)
                        
                st.success(f"Guardado en compras del mes local: {result['name']} ({modalidad_local})")

    st.write("---")
    if st.button("📸 Procesar nueva factura", type="primary"):
        reset_flow()
        st.rerun()

def render_cuentas_por_pagar(client: OdooRPC):
    st.markdown("### 📊 Cuentas por Pagar (Odoo SaaS)")
    st.write("Consulta y registra pagos de tus facturas de compra pendientes en Odoo.")

    # Cargar diarios si no están en state
    if "inv_odoo_journals" not in st.session_state or not st.session_state.inv_odoo_journals:
        try:
            st.session_state.inv_odoo_journals = client.fetch_payment_journals()
        except Exception:
            st.session_state.inv_odoo_journals = []

    try:
        with st.spinner("Obteniendo facturas pendientes de Odoo..."):
            all_bills = client.fetch_unpaid_bills()
            
        # Filtrar facturas creadas por la aplicación
        processed_ids = load_processed_bill_ids()
        bills = [b for b in all_bills if b["id"] in processed_ids]
            
        if not bills:
            st.success("🎉 No tienes facturas pendientes de pago registradas por esta app en Odoo.")
            return

        # Calcular total pendiente
        total_pending = sum(b['amount_residual'] for b in bills)
        st.metric("Total Pendiente en Odoo (Q)", f"Q {total_pending:,.2f}")

        # Agrupar facturas por mes (usando invoice_date_due o invoice_date si no tiene vencimiento)
        # Formato de agrupación: YYYY-MM
        grouped_bills = {}
        for bill in bills:
            date_str = bill['invoice_date_due'] or bill['invoice_date'] or ""
            if date_str:
                try:
                    dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
                    month_key = dt.strftime("%Y-%m")
                    month_label = dt.strftime("%B %Y").capitalize()
                except Exception:
                    month_key = "Sin Fecha"
                    month_label = "Sin Fecha de Vencimiento"
            else:
                month_key = "Sin Fecha"
                month_label = "Sin Fecha de Vencimiento"

            if month_key not in grouped_bills:
                grouped_bills[month_key] = {"label": month_label, "bills": []}
            grouped_bills[month_key]["bills"].append(bill)

        # Ordenar los meses de forma ascendente (el más vencido/cercano primero)
        sorted_month_keys = sorted(list(grouped_bills.keys()))

        # Nombres de meses en español
        meses_es = {
            "January": "Enero", "February": "Febrero", "March": "Marzo", "April": "Abril",
            "May": "Mayo", "June": "Junio", "July": "Julio", "August": "Agosto",
            "September": "Septiembre", "October": "Octubre", "November": "Noviembre", "December": "Diciembre"
        }
        
        for m_key in sorted_month_keys:
            m_data = grouped_bills[m_key]
            lbl = m_data["label"]
            for en, es in meses_es.items():
                if en in lbl:
                    lbl = lbl.replace(en, es)
                    
            st.markdown(f"#### 📅 Vencimiento: {lbl}")
            
            for b in m_data["bills"]:
                with st.expander(f"📄 {b['vendor_name']} | Ref: {b['ref'] or b['name']} | Pendiente: Q {b['amount_residual']:,.2f}"):
                    st.write(f"**Número de Documento (Odoo)**: {b['name']}")
                    st.write(f"**Proveedor**: {b['vendor_name']}")
                    st.write(f"**Referencia / Fac #**: {b['ref'] or 'N/A'}")
                    st.write(f"**Fecha Emisión**: {b['invoice_date']}")
                    st.write(f"**Fecha Vencimiento**: {b['invoice_date_due']}")
                    st.write(f"**Monto Total**: Q {b['amount_total']:,.2f}")
                    st.write(f"**Monto Pendiente (Residual)**: Q {b['amount_residual']:,.2f}")
                    
                    st.markdown("##### 💳 Registrar Pago de Factura")
                    
                    if st.session_state.inv_odoo_journals:
                        col_j, col_d, col_b = st.columns([2, 1.5, 1.5])
                        with col_j:
                            j_opts = {j['id']: f"{j['name']} ({j['code']})" for j in st.session_state.inv_odoo_journals}
                            sel_j_id = st.selectbox(
                                "Diario de Pago:",
                                options=list(j_opts.keys()),
                                format_func=lambda x: j_opts[x],
                                key=f"pay_j_{b['id']}"
                            )
                        with col_d:
                            pay_date = st.date_input("Fecha Pago:", value=datetime.date.today(), key=f"pay_d_{b['id']}")
                        with col_b:
                            st.write("")
                            st.write("")
                            if st.button("Pagar en Odoo", key=f"pay_btn_{b['id']}", use_container_width=True):
                                with st.spinner("Registrando pago contable..."):
                                    try:
                                        client.register_bill_payment(
                                            bill_id=b['id'],
                                            journal_id=sel_j_id,
                                            payment_date=pay_date.strftime("%Y-%m-%d")
                                        )
                                        st.success(f"¡Pago registrado exitosamente para {b['name']}!")
                                        
                                        # Registrar en Semáforo local solo si la factura es de hoy o posterior
                                        try:
                                            b_date = datetime.datetime.strptime(b['invoice_date'], "%Y-%m-%d").date()
                                        except Exception:
                                            b_date = datetime.date.today()
                                            
                                        if b_date >= datetime.date(2026, 6, 24):
                                            if "periodo_actual" in st.session_state:
                                                p = st.session_state.periodo_actual
                                                import uuid
                                                nueva_compra = {
                                                    "id": str(uuid.uuid4()),
                                                    "monto": float(b['amount_residual']),
                                                    "proveedor": b['vendor_name'],
                                                    "fecha": pay_date.strftime("%Y-%m-%d"),
                                                    "nota": f"Pago diferido Odoo Fac: {b['ref'] or b['name']}",
                                                    "modalidad": "Contado"
                                                }
                                                p["compras"].append(nueva_compra)
                                                st.toast("Registrado en compras locales del semáforo.")
                                        else:
                                            st.toast("Factura anterior a hoy. Se omitió el registro local.")
                                        
                                        st.rerun()
                                    except Exception as err:
                                        st.error(f"Error al registrar pago: {str(err)}")
                    else:
                        st.info("Carga diarios de pago para asentar el pago.")

    except Exception as e:
        st.error(f"⚠️ Error al obtener cuentas por pagar de Odoo: {str(e)}")
