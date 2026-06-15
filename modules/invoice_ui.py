"""
Módulo de la interfaz de usuario en Streamlit para el flujo de Factura OCR e integración con Odoo.
"""

import streamlit as st
import pandas as pd
import os
from typing import Dict, Any, List, Optional
from modules.odoo_connector import OdooRPC, OdooAuthError, OdooConnectionError, OdooValidationError
from modules.invoice_ocr import extract_invoice_data
from modules.rules_matrix import find_matching_rule, create_or_update_rule

def get_odoo_client() -> Optional[OdooRPC]:
    """Crea una instancia del cliente Odoo utilizando las variables del entorno o st.secrets."""
    url = os.getenv("ODOO_URL") or st.secrets.get("ODOO_URL")
    db = os.getenv("ODOO_DB") or st.secrets.get("ODOO_DB")
    username = os.getenv("ODOO_USERNAME") or st.secrets.get("ODOO_USERNAME")
    api_key = os.getenv("ODOO_API_KEY") or st.secrets.get("ODOO_API_KEY")
    
    if not all([url, db, username, api_key]):
        return None
    return OdooRPC(url, db, username, api_key)

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
    if "inv_po_result" not in st.session_state:
        st.session_state.inv_po_result = None
    if "inv_odoo_vendors" not in st.session_state:
        st.session_state.inv_odoo_vendors = []
    if "inv_odoo_taxes" not in st.session_state:
        st.session_state.inv_odoo_taxes = []
    if "inv_odoo_products" not in st.session_state:
        st.session_state.inv_odoo_products = []
    if "inv_odoo_connected" not in st.session_state:
        st.session_state.inv_odoo_connected = False
    if "inv_creating_po" not in st.session_state:
        st.session_state.inv_creating_po = False
    if "inv_rules_to_save" not in st.session_state:
        st.session_state.inv_rules_to_save = []

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
    st.session_state.inv_po_result = None
    st.session_state.inv_creating_po = False
    st.session_state.inv_rules_to_save = []

def render_invoice_tab():
    initialize_state()

    st.markdown("## 📸 Integración Odoo — Facturación de Compra OCR")
    st.markdown(
        "Sube una foto de la factura de compra física de tu proveedor. "
        "La IA extraerá las líneas de productos, las validará contra Odoo y creará un borrador de Orden de Compra (RFQ)."
    )

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
        render_step_5()

def render_step_1(client: OdooRPC):
    st.markdown("### Paso 1: Selección de Proveedor y Carga de Imagen")
    
    # Dropdown de proveedores
    vendors = st.session_state.inv_odoo_vendors
    vendor_options = {v['id']: v['name'] for v in vendors}
    
    selected_vendor_id = st.selectbox(
        "Selecciona el Proveedor:",
        options=list(vendor_options.keys()),
        format_func=lambda x: vendor_options[x],
        index=0 if not st.session_state.inv_vendor_id else list(vendor_options.keys()).index(st.session_state.inv_vendor_id)
    )

    uploaded_file = st.file_uploader(
        "Toma una foto o sube la factura de compra:",
        type=["jpg", "jpeg", "png", "webp"],
        help="Optimizado para capturas desde cámara de celular."
    )

    if uploaded_file:
        file_bytes = uploaded_file.read()
        st.session_state.inv_image_bytes = file_bytes
        st.image(file_bytes, caption="Factura cargada", width=350)

    if st.button("🔍 Extraer Datos con IA", type="primary", disabled=(not uploaded_file)):
        st.session_state.inv_vendor_id = selected_vendor_id
        st.session_state.inv_vendor_name = vendor_options[selected_vendor_id]
        
        try:
            with st.spinner("La IA (Gemini) está leyendo tu factura..."):
                extracted = extract_invoice_data(st.session_state.inv_image_bytes, uploaded_file.type)
                st.session_state.inv_extracted_data = extracted
                st.session_state.inv_invoice_number = extracted.get("invoice_number") or ""
                
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
                    if rule:
                        orig_qty = qty
                        qty = qty * rule["quantity_multiplier"]
                        # Si cambia cantidad, ajustamos proporcionalmente el precio unitario
                        if rule["quantity_multiplier"] != 0:
                            price = price / rule["quantity_multiplier"]
                        applied_rule = True
                    
                    processed_lines.append({
                        "original_description": orig_desc,
                        "description": rule["converted_description"] if rule else orig_desc,
                        "quantity": float(qty),
                        "price_unit": float(price),
                        "supplier_code": sup_code,
                        "applied_rule": applied_rule,
                        "multiplier": rule["quantity_multiplier"] if rule else 1.0,
                        "odoo_product_id": rule["odoo_product_id"] if rule else None,
                        "odoo_default_code": rule["odoo_default_code"] if rule else ""
                    })
                
                st.session_state.inv_edited_lines = processed_lines
                st.session_state.inv_step = 2
                st.rerun()
        except Exception as e:
            st.error(f"❌ Error durante la extracción: {str(e)}")

def render_step_2():
    st.markdown("### Paso 2: Validación e ingreso de datos")
    st.write(f"**Proveedor seleccionado**: {st.session_state.inv_vendor_name}")
    
    st.session_state.inv_invoice_number = st.text_input(
        "Número de Factura / Referencia:", 
        value=st.session_state.inv_invoice_number
    )

    st.markdown("#### Líneas de Compra Extraídas")
    st.info("💡 Puedes editar directamente en las celdas. Modifica las descripciones si deseas que se asocien a un producto distinto.")

    df_lines = pd.DataFrame(st.session_state.inv_edited_lines)
    if df_lines.empty:
        st.warning("No se extrajeron líneas. Agrega una nueva línea.")
        df_lines = pd.DataFrame(columns=["description", "quantity", "price_unit", "supplier_code"])

    # Selector y editor de tabla
    edited_df = st.data_editor(
        df_lines[["description", "quantity", "price_unit", "supplier_code"]],
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "description": st.column_config.TextColumn("Descripción del Producto (Odoo / Factura)", required=True),
            "quantity": st.column_config.NumberColumn("Cantidad", min_value=0.01, required=True, format="%.2f"),
            "price_unit": st.column_config.NumberColumn("Precio Unitario (Q)", min_value=0.0, required=True, format="Q %.2f"),
            "supplier_code": st.column_config.TextColumn("Código Proveedor"),
        }
    )

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
            st.rerun()

def render_step_3(client: OdooRPC):
    st.markdown("### Paso 3: Vinculación de Productos en Odoo")
    st.write("Verificando si los ítems existen en el catálogo de tu Odoo...")

    # Realizar matching si está vacío
    if not st.session_state.inv_product_matches:
        matches = []
        with st.spinner("Buscando coincidencias en Odoo..."):
            for line in st.session_state.inv_edited_lines:
                match = None
                # Si ya tiene un id pre-asociado por regla, buscar detalles directos
                if line.get("odoo_product_id"):
                    try:
                        match = client.get_product_details(line["odoo_product_id"])
                    except Exception:
                        pass
                
                # De lo contrario, buscar por descripción
                if not match:
                    match = client.search_product(line["description"], st.session_state.inv_vendor_id)

                if match:
                    matches.append({
                        "line_desc": line["description"],
                        "found": True,
                        "product_id": match["id"],
                        "odoo_name": match["name"],
                        "uom_id": match["uom_id"],
                        "default_code": match.get("default_code") or "",
                        "action": "use_existing"
                    })
                else:
                    matches.append({
                        "line_desc": line["description"],
                        "found": False,
                        "product_id": None,
                        "odoo_name": "",
                        "uom_id": 1, # UoM Unidad por defecto
                        "default_code": line["supplier_code"] or "",
                        "action": "create_new"
                    })
        st.session_state.inv_product_matches = matches

    # Mostrar preview y permitir modificaciones
    st.markdown("#### Coincidencias encontradas")
    
    has_creations = False
    for i, match in enumerate(st.session_state.inv_product_matches):
        line = st.session_state.inv_edited_lines[i]
        
        col_desc, col_match, col_action = st.columns([2, 2, 1])
        
        with col_desc:
            st.write(f"**Línea**: `{line['description']}` (Cant: {line['quantity']} | Unit: Q {line['price_unit']:.2f})")
            
        with col_match:
            if match["found"] and match.get("action", "use_existing") == "use_existing":
                st.success(f"✅ Odoo Match: **[{match['default_code']}] {match['odoo_name']}**")
            elif match.get("action") == "map_existing" and match.get("manually_mapped"):
                st.info(f"🔗 Vinculado a: **[{match['default_code']}] {match['odoo_name']}**")
            else:
                st.warning("⚠️ No se encontró coincidencia en Odoo.")
                
        with col_action:
            action_options = ["use_existing", "create_new", "map_existing"]
            action_labels = {
                "use_existing": "Usar Match Sugerido" if match["found"] else "Sin coincidencia",
                "create_new": "Crear Nuevo",
                "map_existing": "Buscar Catálogo"
            }
            
            # Si no se encontró match inicialmente, deshabilitar o no sugerir "use_existing" como primera opción
            idx_default = 0
            if not match["found"]:
                # Si no hay match sugerido, la acción por defecto es "create_new" (índice 1)
                idx_default = 1
                
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
                # Buscar índice del producto ya seleccionado si existe
                current_id = match.get("product_id")
                default_idx = 0
                if current_id:
                    for idx, p in enumerate(products):
                        if p["id"] == current_id:
                            default_idx = idx
                            break
                            
                selected_p = st.selectbox(
                    "Selecciona el producto existente de Odoo:",
                    options=products,
                    format_func=get_prod_label,
                    index=default_idx,
                    key=f"map_p_{i}"
                )
                if selected_p:
                    match["product_id"] = selected_p["id"]
                    match["odoo_name"] = selected_p["name"]
                    match["default_code"] = selected_p.get("default_code") or ""
                    match["manually_mapped"] = True

        st.markdown("---")

    # Botones
    col_prev, col_next = st.columns([1, 1])
    with col_prev:
        if st.button("← Atrás"):
            st.session_state.inv_product_matches = [] # reset matches para recalcular
            st.session_state.inv_step = 2
            st.rerun()
            
    with col_next:
        confirm_text = "Confirmar y Crear PO" if not has_creations else "Crear Productos Nuevos y PO"
        if st.button(confirm_text, type="primary"):
            st.session_state.inv_step = 4
            st.rerun()

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
            product_id = match["product_id"]

            # 1. Crear producto si se seleccionó "create_new"
            if match["action"] == "create_new":
                with st.spinner(f"Creando producto '{match['new_name']}' en Odoo..."):
                    product_id = client.create_product(
                        name=match["new_name"],
                        default_code=match["new_code"],
                        detailed_type='product',
                        purchase_tax_ids=default_tax_ids,
                        vendor_id=st.session_state.inv_vendor_id,
                        vendor_price=line["price_unit"],
                        vendor_code=match["new_code"]
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
        with st.spinner("Creando Orden de Compra (RFQ) en Odoo..."):
            po_result = client.create_purchase_order(
                vendor_id=st.session_state.inv_vendor_id,
                lines=po_lines
            )
            st.session_state.inv_po_result = po_result
            st.session_state.inv_rules_to_save = rules_to_save
            
            # Guardar reglas locales
            for r in rules_to_save:
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
        st.rerun()

    except Exception as e:
        st.session_state.inv_creating_po = False
        st.error(f"❌ Error al procesar en Odoo: {str(e)}")
        if st.button("Volver al paso anterior"):
            st.session_state.inv_step = 3
            st.rerun()

def render_step_5():
    st.markdown("### ¡Orden de Compra Creada Correctamente! 🎉")
    
    result = st.session_state.inv_po_result
    if result:
        st.markdown(f"**Referencia Odoo**: `{result['name']}`")
        st.markdown(f"**Monto Total (RFQ)**: `Q {result['amount_total']:.2f}`")
        
        odoo_url = os.getenv("ODOO_URL")
        web_link = f"{odoo_url}/web#id={result['id']}&model=purchase.order&view_type=form"
        
        st.markdown(f"[🔗 Abrir en Odoo]({web_link})")
        
        # Ofrecer vincular esta compra con el presupuesto de FerreCheck
        st.write("---")
        st.markdown("#### ¿Registrar en el presupuesto local de FerreCheck?")
        st.write("Si lo deseas, puedes agregar el total de esta compra a tu Semáforo de compras local.")
        
        if st.button("📥 Registrar localmente en compras", type="secondary"):
            # Obtener el período actual de la app principal
            if "periodo_actual" in st.session_state:
                p = st.session_state.periodo_actual
                import uuid
                nueva_compra = {
                    "id": str(uuid.uuid4()),
                    "monto": float(result['amount_total']),
                    "proveedor": st.session_state.inv_vendor_name,
                    "fecha": datetime.date.today().strftime("%Y-%m-%d"),
                    "nota": f"Importado de Odoo PO {result['name']}",
                    "modalidad": "Contado"
                }
                p["compras"].append(nueva_compra)
                st.success(f"Guardado en compras del mes local: {result['name']}")

    if st.button("📸 Procesar nueva factura", type="primary"):
        reset_flow()
        st.rerun()
