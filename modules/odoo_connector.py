"""
Módulo de conexión XML-RPC con Odoo Online para la creación de compras y productos.
"""

import xmlrpc.client
import datetime
import logging
import re
from typing import List, Dict, Any, Optional

# Configurar logger
logger = logging.getLogger("ferrecheck.odoo")
logging.basicConfig(level=logging.INFO)

class OdooConnectionError(Exception):
    """Excepción para errores de conexión de red o servidor inaccesible."""
    pass

class OdooAuthError(Exception):
    """Excepción para credenciales inválidas o falta de permisos."""
    pass

class OdooValidationError(Exception):
    """Excepción para errores de validación de modelos en Odoo."""
    pass


class OdooRPC:
    def __init__(self, url: str, db: str, username: str, api_key: str):
        self.url = url.rstrip('/')
        self.db = db
        self.username = username
        self.api_key = api_key
        self.uid = None
        self._models = None

    def connect(self) -> bool:
        """
        Autentica y establece conexión con Odoo.
        Retorna True si la conexión fue exitosa.
        """
        try:
            common = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common", allow_none=True)
            self.uid = common.authenticate(self.db, self.username, self.api_key, {})
            if not self.uid:
                raise OdooAuthError("Autenticación fallida en Odoo. Verifique las credenciales.")
            
            self._models = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object", allow_none=True)
            return True
        except xmlrpc.client.Fault as e:
            raise OdooAuthError(f"Error de protocolo Odoo XML-RPC: {e.faultString}")
        except Exception as e:
            raise OdooConnectionError(f"No se pudo conectar a Odoo: {str(e)}")

    def _execute(self, model: str, method: str, *args, **kwargs) -> Any:
        """Wrapper interno para ejecutar llamadas remotas."""
        if not self._models or not self.uid:
            self.connect()
        try:
            return self._models.execute_kw(self.db, self.uid, self.api_key, model, method, *args, **kwargs)
        except xmlrpc.client.Fault as e:
            err_msg = e.faultString
            if "AccessDenied" in err_msg or "Access Denied" in err_msg:
                raise OdooAuthError(f"Permiso denegado en Odoo: {err_msg}")
            elif "ValidationError" in err_msg or "UserError" in err_msg:
                raise OdooValidationError(f"Error de validación en Odoo: {err_msg}")
            else:
                raise OdooValidationError(f"Error en operación de Odoo: {err_msg}")
        except Exception as e:
            raise OdooConnectionError(f"Error de comunicación XML-RPC: {str(e)}")

    def fetch_vendors(self) -> List[Dict[str, Any]]:
        """
        Obtiene los proveedores activos (res.partner con supplier_rank > 0).
        """
        domain = [('supplier_rank', '>', 0), ('active', '=', True)]
        fields = ['id', 'name', 'email', 'vat']
        return self._execute('res.partner', 'search_read', [domain], {'fields': fields, 'order': 'name asc'})

    def fetch_purchase_taxes(self) -> List[Dict[str, Any]]:
        """
        Obtiene los impuestos de tipo compra activos.
        """
        domain = [('type_tax_use', '=', 'purchase'), ('active', '=', True)]
        fields = ['id', 'name', 'amount']
        return self._execute('account.tax', 'search_read', [domain], {'fields': fields})

    def fetch_all_products(self) -> List[Dict[str, Any]]:
        """
        Obtiene una lista ligera de todos los productos (product.product) activos.
        """
        domain = [('active', '=', True)]
        fields = ['id', 'name', 'default_code', 'list_price']
        return self._execute('product.product', 'search_read', [domain], {'fields': fields, 'order': 'name asc'})

    def search_product(self, query: str, vendor_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """
        Busca un producto por código interno (default_code) o por nombre.
        Si se especifica vendor_id, busca también por código de proveedor en product.supplierinfo.
        """
        # 1. Buscar por default_code exacto
        clean_query = query.strip()
        matches = self._execute('product.product', 'search_read', 
                                [[('default_code', '=', clean_query)]], 
                                {'fields': ['id', 'name', 'uom_id', 'product_tmpl_id', 'list_price', 'default_code'], 'limit': 1})
        if matches:
            return self._format_product_match(matches[0])

        # 2. Si hay proveedor, buscar en product.supplierinfo por código de proveedor
        if vendor_id:
            supp_domain = [('partner_id', '=', vendor_id), ('product_code', '=', clean_query)]
            supp_matches = self._execute('product.supplierinfo', 'search_read',
                                         [supp_domain], {'fields': ['product_tmpl_id'], 'limit': 1})
            if supp_matches:
                tmpl_id = supp_matches[0]['product_tmpl_id'][0]
                prod_matches = self._execute('product.product', 'search_read',
                                             [[('product_tmpl_id', '=', tmpl_id)]],
                                             {'fields': ['id', 'name', 'uom_id', 'product_tmpl_id', 'list_price', 'default_code'], 'limit': 1})
                if prod_matches:
                    return self._format_product_match(prod_matches[0])

        # 3. Buscar por coincidencia parcial en el nombre completa primero
        matches = self._execute('product.product', 'search_read', 
                                [[('name', 'ilike', clean_query)]], 
                                {'fields': ['id', 'name', 'uom_id', 'product_tmpl_id', 'list_price', 'default_code'], 'limit': 1})
        if matches:
            return self._format_product_match(matches[0])

        # 4. Coincidencia inteligente por palabras (tokens)
        stop_words = {'de', 'del', 'con', 'para', 'por', 'sin', 'los', 'las', 'una', 'uno', 'unos', 'unas', 'con', 'y', 'o', 'el', 'la', 'en'}
        words = re.findall(r'\b\w+\b', clean_query.lower())
        significant_words = [w for w in words if w not in stop_words and len(w) >= 3]

        if significant_words:
            # Ordenar por longitud de mayor a menor (las palabras más largas suelen ser más específicas)
            significant_words.sort(key=len, reverse=True)
            
            # Intento A: Que contenga todas las palabras significativas en cualquier orden
            domain_and = []
            for w in significant_words:
                domain_and.append(('name', 'ilike', w))
            
            matches = self._execute('product.product', 'search_read', 
                                    [domain_and], 
                                    {'fields': ['id', 'name', 'uom_id', 'product_tmpl_id', 'list_price', 'default_code'], 'limit': 1})
            if matches:
                return self._format_product_match(matches[0])

            # Intento B: Si hay más de 2 palabras significativas, intentar con las 2 más largas (las descriptivas principales)
            if len(significant_words) > 2:
                top_2_words = significant_words[:2]
                domain_top_2 = [('name', 'ilike', w) for w in top_2_words]
                matches = self._execute('product.product', 'search_read', 
                                        [domain_top_2], 
                                        {'fields': ['id', 'name', 'uom_id', 'product_tmpl_id', 'list_price', 'default_code'], 'limit': 1})
                if matches:
                    return self._format_product_match(matches[0])

        return None

    def find_product_by_code(self, code: str, vendor_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """
        Busca un producto en Odoo usando un código específico (proveedor o interno).
        Compara contra:
        1. default_code (Referencia Interna) de product.product
        2. barcode (Código de barras) de product.product
        3. product_code en product.supplierinfo (si se provee vendor_id)
        """
        if not code:
            return None
        
        clean_code = str(code).strip()
        fields = ['id', 'name', 'uom_id', 'product_tmpl_id', 'list_price', 'default_code']

        # 1. Buscar por default_code exacto
        matches = self._execute('product.product', 'search_read', 
                                [[('default_code', '=', clean_code)]], 
                                {'fields': fields, 'limit': 1})
        if matches:
            return self._format_product_match(matches[0])

        # 2. Buscar por barcode exacto
        matches = self._execute('product.product', 'search_read', 
                                [[('barcode', '=', clean_code)]], 
                                {'fields': fields, 'limit': 1})
        if matches:
            return self._format_product_match(matches[0])

        # 3. Buscar en product.supplierinfo por código de proveedor
        if vendor_id:
            supp_domain = [('partner_id', '=', vendor_id), ('product_code', '=', clean_code)]
            supp_matches = self._execute('product.supplierinfo', 'search_read',
                                         [supp_domain], {'fields': ['product_tmpl_id'], 'limit': 1})
            if supp_matches:
                tmpl_id = supp_matches[0]['product_tmpl_id'][0]
                prod_matches = self._execute('product.product', 'search_read',
                                             [[('product_tmpl_id', '=', tmpl_id)]],
                                             {'fields': fields, 'limit': 1})
                if prod_matches:
                    return self._format_product_match(prod_matches[0])

        return None

    def get_product_details(self, product_id: int) -> Dict[str, Any]:
        """
        Obtiene los detalles del producto por su ID (product.product).
        """
        fields = ['id', 'name', 'uom_id', 'product_tmpl_id', 'list_price', 'default_code']
        res = self._execute('product.product', 'read', [[product_id]], {'fields': fields})
        if res:
            return self._format_product_match(res[0])
        raise OdooValidationError(f"No se encontró el producto con ID {product_id} en Odoo.")

    def update_product_sale_price(self, product_id: int, new_price: float) -> bool:
        """
        Actualiza el precio de venta (list_price) del producto en Odoo.
        """
        return self._execute('product.product', 'write', [[product_id], {'list_price': float(new_price)}])

    def update_product_pricelist_item(self, product_tmpl_id: int, min_quantity: float, new_price: float, pricelist_id: int = 1) -> bool:
        """
        Actualiza o crea un descuento por volumen en Odoo.
        """
        # Buscar si ya existe una regla exacta
        domain = [
            ('product_tmpl_id', '=', product_tmpl_id),
            ('pricelist_id', '=', pricelist_id),
            ('min_quantity', '=', float(min_quantity))
        ]
        items = self._execute('product.pricelist.item', 'search', [domain])
        if items:
            # Actualizar existente
            return self._execute('product.pricelist.item', 'write', [items, {'fixed_price': float(new_price)}])
        else:
            # Crear nueva regla
            return self._execute('product.pricelist.item', 'create', [{
                'product_tmpl_id': product_tmpl_id,
                'pricelist_id': pricelist_id,
                'min_quantity': float(min_quantity),
                'fixed_price': float(new_price),
                'compute_price': 'fixed'
            }])

    def _format_product_match(self, raw_prod: Dict[str, Any]) -> Dict[str, Any]:
        """Extrae los IDs de las tuplas Many2one para simplificar el uso."""
        uom_raw = raw_prod.get('uom_id')
        tmpl_raw = raw_prod.get('product_tmpl_id')
        return {
            'id': raw_prod['id'],
            'name': raw_prod['name'],
            'uom_id': uom_raw[0] if isinstance(uom_raw, (list, tuple)) else uom_raw,
            'uom_name': uom_raw[1] if isinstance(uom_raw, (list, tuple)) else "",
            'product_tmpl_id': tmpl_raw[0] if isinstance(tmpl_raw, (list, tuple)) else tmpl_raw,
            'list_price': raw_prod.get('list_price', 0.0),
            'default_code': raw_prod.get('default_code') or ""
        }

    def create_product(self, name: str, default_code: str, type: str = 'product', 
                       purchase_tax_ids: Optional[List[int]] = None, vendor_id: Optional[int] = None, 
                       vendor_price: float = 0.0, vendor_code: Optional[str] = None,
                       sale_price: Optional[float] = None, categ_id: Optional[int] = None,
                       available_in_pos: bool = True, image_base64: Optional[str] = None) -> int:
        """
        Crea un nuevo producto en Odoo (vía product.template).
        Auto-asocia el proveedor y los impuestos por defecto.
        Retorna el ID del product.product variante auto-creado.
        """
        vals: Dict[str, Any] = {
            'name': name.strip(),
            'type': type,
            'detailed_type': type,
            'is_storable': True,  # Rastrear en inventario / Control de Stock
            'default_code': default_code.strip() if default_code else False,
            'list_price': sale_price if sale_price is not None else vendor_price,
            'standard_price': vendor_price,  # Costo
            'sale_ok': True,
            'purchase_ok': True,
            'available_in_pos': available_in_pos,
        }

        if categ_id:
            vals['categ_id'] = categ_id

        if image_base64:
            vals['image_1920'] = image_base64

        if purchase_tax_ids:
            vals['supplier_taxes_id'] = [(6, 0, purchase_tax_ids)]

        if vendor_id:
            vals['seller_ids'] = [
                (0, 0, {
                    'partner_id': vendor_id,
                    'price': vendor_price,
                    'min_qty': 1.0,
                    'product_code': vendor_code.strip() if vendor_code else False,
                })
            ]

        tmpl_id = self._execute('product.template', 'create', [vals])
        
        # Buscar el product.product asociado al template
        prod_ids = self._execute('product.product', 'search', [[('product_tmpl_id', '=', tmpl_id)]])
        if not prod_ids:
            raise OdooValidationError("El producto fue creado pero no se encontró su variante de stock correspondiente.")
        return prod_ids[0]

    def create_purchase_order(self, vendor_id: int, lines: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Crea una orden de compra en estado borrador (draft RFQ).
        lines debe ser una lista de dicts:
        [
            {
                'product_id': int,
                'name': str (descripción de la línea),
                'product_qty': float,
                'price_unit': float,
                'product_uom': int,
                'taxes_id': Optional[List[int]]
            }
        ]
        """
        order_lines = []
        for line in lines:
            line_vals = {
                'product_id': line['product_id'],
                'name': line['name'],
                'product_qty': float(line['product_qty']),
                'price_unit': float(line['price_unit']),
                'product_uom_id': line['product_uom'],
            }
            if line.get('taxes_id'):
                line_vals['tax_ids'] = [(6, 0, line['taxes_id'])]
            
            # Fecha planificada por defecto: hoy
            line_vals['date_planned'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            order_lines.append((0, 0, line_vals))

        po_vals = {
            'partner_id': vendor_id,
            'date_order': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'order_line': order_lines,
        }

        po_id = self._execute('purchase.order', 'create', [po_vals])
        
        # Leer datos resultantes para confirmar
        po_info = self._execute('purchase.order', 'read', [[po_id]], {'fields': ['name', 'amount_total']})
        return {
            'id': po_id,
            'name': po_info[0]['name'] if po_info else f"PO-{po_id}",
            'amount_total': po_info[0]['amount_total'] if po_info else 0.0
        }

    def confirm_purchase_order(self, po_id: int) -> bool:
        """
        Confirma la orden de compra (pasa de RFQ a Purchase Order).
        """
        self._execute('purchase.order', 'button_confirm', [[po_id]])
        return True

    def validate_incoming_picking(self, po_id: int) -> bool:
        """
        Busca el albarán/picking de inventario asociado a la PO y lo valida al 100%.
        """
        # 1. Buscar picking asociado a la PO que no esté en estado 'done' o 'cancel'
        pickings = self._execute('stock.picking', 'search_read', 
                                 [[('purchase_id', '=', po_id), ('state', 'not in', ['done', 'cancel'])]], 
                                 {'fields': ['id', 'name']})
        if not pickings:
            return True
            
        picking_ids = [p['id'] for p in pickings]
        
        # 2. Escribir la cantidad realizada (quantity) igual a la cantidad demandada (product_uom_qty)
        # En Odoo 17/18/19, la cantidad realizada en stock.move se guarda en 'quantity'
        moves = self._execute('stock.move', 'search_read',
                              [[('picking_id', 'in', picking_ids)]],
                              {'fields': ['id', 'product_uom_qty']})
        for move in moves:
            self._execute('stock.move', 'write', [[move['id']], {'quantity': float(move['product_uom_qty'])}])
            
        # 3. Validar el picking
        self._execute('stock.picking', 'button_validate', [picking_ids])
        return True

    def create_and_post_vendor_bill(self, po_id: int, invoice_date: str, due_date: str, invoice_ref: str) -> int:
        """
        Crea la factura del proveedor (bill) asociada al PO, establece fechas y la publica (post).
        Retorna el ID del move de factura creado.
        """
        # 1. Crear el bill desde el PO
        action = self._execute('purchase.order', 'action_create_invoice', [[po_id]])
        
        # 2. Buscar la factura asociada (account.move)
        bill_id = action.get('res_id')
        if not bill_id:
            po_info = self._execute('purchase.order', 'read', [[po_id]], {'fields': ['name']})
            po_name = po_info[0]['name'] if po_info else ""
            bills = self._execute('account.move', 'search', [[('invoice_origin', '=', po_name)]])
            if bills:
                bill_id = bills[0]
                
        if not bill_id:
            raise OdooValidationError("No se pudo encontrar o generar la factura del proveedor en Odoo.")
            
        # 3. Actualizar fechas y referencia de la factura
        write_vals = {
            'invoice_date': invoice_date,
            'invoice_date_due': due_date,
            'ref': invoice_ref.strip() if invoice_ref else False
        }
        self._execute('account.move', 'write', [[bill_id], write_vals])
        
        # 4. Publicar la factura
        self._execute('account.move', 'action_post', [[bill_id]])
        return bill_id

    def fetch_payment_journals(self) -> List[Dict[str, Any]]:
        """
        Obtiene los diarios contables activos tipo banco o caja de Odoo.
        """
        domain = [('type', 'in', ['bank', 'cash']), ('active', '=', True)]
        fields = ['id', 'name', 'type', 'code']
        return self._execute('account.journal', 'search_read', [domain], {'fields': fields})

    def fetch_categories(self) -> List[Dict[str, Any]]:
        """
        Obtiene las categorías de productos disponibles en Odoo.
        """
        domain = []
        fields = ['id', 'name']
        return self._execute('product.category', 'search_read', [domain], {'fields': fields})

    def register_bill_payment(self, bill_id: int, journal_id: int, payment_date: str) -> bool:
        """
        Registra el pago manual de la factura de proveedor.
        """
        # 1. Leer detalles de la factura para saber el total y la moneda
        bill = self._execute('account.move', 'read', [[bill_id]], {'fields': ['amount_residual', 'currency_id']})
        if not bill:
            raise OdooValidationError("No se encontró la factura a pagar.")
            
        amount = bill[0]['amount_residual']
        currency_id = bill[0]['currency_id'][0] if isinstance(bill[0]['currency_id'], (list, tuple)) else bill[0]['currency_id']
        
        # 2. Buscar el método de pago por defecto para el diario
        journal = self._execute('account.journal', 'read', [[journal_id]], {'fields': ['outbound_payment_method_line_ids']})
        pay_method_line_id = False
        if journal and journal[0].get('outbound_payment_method_line_ids'):
            pay_method_line_id = journal[0]['outbound_payment_method_line_ids'][0]
            
        wizard_vals = {
            'payment_date': payment_date,
            'amount': float(amount),
            'payment_type': 'outbound',
            'partner_type': 'supplier',
            'journal_id': journal_id,
            'currency_id': currency_id
        }
        if pay_method_line_id:
            wizard_vals['payment_method_line_id'] = pay_method_line_id
            
        # 3. Crear el wizard de registro de pago
        context = {
            'active_model': 'account.move',
            'active_ids': [bill_id]
        }
        wizard_id = self._execute('account.payment.register', 'create', [wizard_vals], {'context': context})
        
        # 4. Asentar los pagos
        self._execute('account.payment.register', 'action_create_payments', [[wizard_id]])
        return True

    def create_reordering_rule(self, product_id: int, min_qty: float, max_qty: float) -> int:
        """
        Crea una regla de reabastecimiento (stock.warehouse.orderpoint) para un producto.
        """
        # Buscar el almacén principal
        warehouses = self._execute('stock.warehouse', 'search', [[]])
        warehouse_id = warehouses[0] if warehouses else False
        
        # Buscar la primera ubicación interna
        locations = self._execute('stock.location', 'search', [[('usage', '=', 'internal')]])
        location_id = locations[0] if locations else False
        
        vals = {
            'product_id': product_id,
            'product_min_qty': float(min_qty),
            'product_max_qty': float(max_qty),
            'trigger': 'auto'
        }
        if warehouse_id:
            vals['warehouse_id'] = warehouse_id
        if location_id:
            vals['location_id'] = location_id
            
        return self._execute('stock.warehouse.orderpoint', 'create', [vals])

    def fetch_unpaid_bills(self) -> List[Dict[str, Any]]:
        """
        Obtiene las facturas de proveedor publicadas y no pagadas.
        """
        domain = [
            ('move_type', '=', 'in_invoice'),
            ('state', '=', 'posted'),
            ('payment_state', 'in', ['not_paid', 'partial'])
        ]
        fields = ['id', 'name', 'invoice_date', 'invoice_date_due', 'partner_id', 'amount_total', 'amount_residual', 'ref']
        bills = self._execute('account.move', 'search_read', [domain], {'fields': fields, 'order': 'invoice_date_due asc'})
        
        formatted_bills = []
        for bill in bills:
            partner = bill.get('partner_id')
            partner_name = partner[1] if isinstance(partner, (list, tuple)) else (partner or "")
            formatted_bills.append({
                'id': bill['id'],
                'name': bill['name'],
                'invoice_date': bill.get('invoice_date') or "",
                'invoice_date_due': bill.get('invoice_date_due') or "",
                'vendor_name': partner_name,
                'amount_total': bill.get('amount_total', 0.0),
                'amount_residual': bill.get('amount_residual', 0.0),
                'ref': bill.get('ref') or ""
            })
        return formatted_bills

    def fetch_sales_history_by_product(self, months: int = 12) -> List[Dict[str, Any]]:
        """
        Obtiene el historial de líneas de venta (sale.order.line) de los últimos N meses.
        """
        import datetime
        from dateutil.relativedelta import relativedelta
        
        start_date = datetime.date.today() - relativedelta(months=months)
        start_date_str = start_date.strftime('%Y-%m-01 00:00:00')
        
        domain = [
            ('order_id.state', 'in', ['paid', 'done', 'invoiced']),
            ('product_id.active', '=', True),
            ('order_id.date_order', '>=', start_date_str)
        ]
        
        fields = ['id', 'product_id', 'qty', 'order_id']
        lines = self._execute('pos.order.line', 'search_read', [domain], {'fields': fields})
        
        formatted_lines = []
        for line in lines:
            prod_tuple = line.get('product_id', [False, ""])
            order_tuple = line.get('order_id', [False, ""])
            
            formatted_lines.append({
                'id': line.get('id'),
                'product_id': prod_tuple,
                'product_uom_qty': line.get('qty', 0.0),
                'order_id': order_tuple[0] if isinstance(order_tuple, list) else order_tuple
            })
            
        order_ids = list(set([l['order_id'] for l in formatted_lines if l['order_id']]))
        if not order_ids:
            return []
            
        orders = self._execute('pos.order', 'search_read', [[('id', 'in', order_ids)]], {'fields': ['id', 'date_order']})
        order_date_map = {o['id']: o.get('date_order') for o in orders}
        
        product_ids = list(set([l['product_id'][0] for l in formatted_lines if isinstance(l['product_id'], list)]))
        products = self._execute('product.product', 'search_read', [[('id', 'in', product_ids)]], {'fields': ['id', 'default_code']})
        prod_code_map = {p['id']: p.get('default_code', '') for p in products}
        
        for l in formatted_lines:
            l['date_order'] = order_date_map.get(l['order_id'])
            if isinstance(l['product_id'], list) and l['product_id']:
                l['default_code'] = prod_code_map.get(l['product_id'][0], '')
            else:
                l['default_code'] = ''
                
        return formatted_lines

    def fetch_products_stock(self, product_ids: List[int]) -> Dict[int, Dict[str, Any]]:
        """
        Consulta qty_available en product.product para una lista de IDs.
        Retorna {product_id: {"name": ..., "code": ..., "stock": ..., "uom": ...}}
        """
        if not product_ids:
            return {}
            
        domain = [('id', 'in', product_ids)]
        fields = ['id', 'name', 'default_code', 'qty_available', 'uom_id']
        products = self._execute('product.product', 'search_read', [domain], {'fields': fields})
        
        result = {}
        for p in products:
            uom = p.get('uom_id', [False, "Unidades"])
            result[p['id']] = {
                "name": p.get('name', ''),
                "code": p.get('default_code') or '',
                "stock": float(p.get('qty_available', 0.0)),
                "uom": uom[1] if isinstance(uom, list) else str(uom)
            }
        return result
