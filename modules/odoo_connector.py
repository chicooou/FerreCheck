"""
Módulo de conexión XML-RPC con Odoo Online para la creación de compras y productos.
"""

import xmlrpc.client
import datetime
import logging
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

    def search_product(self, query: str, vendor_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """
        Busca un producto por código interno (default_code) o por nombre.
        Si se especifica vendor_id, busca también por código de proveedor en product.supplierinfo.
        """
        # 1. Buscar por default_code exacto
        clean_query = query.strip()
        matches = self._execute('product.product', 'search_read', 
                                [[('default_code', '=', clean_query)]], 
                                {'fields': ['id', 'name', 'uom_id', 'product_tmpl_id'], 'limit': 1})
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
                                             {'fields': ['id', 'name', 'uom_id', 'product_tmpl_id'], 'limit': 1})
                if prod_matches:
                    return self._format_product_match(prod_matches[0])

        # 3. Buscar por coincidencia parcial en el nombre
        matches = self._execute('product.product', 'search_read', 
                                [[('name', 'ilike', clean_query)]], 
                                {'fields': ['id', 'name', 'uom_id', 'product_tmpl_id'], 'limit': 1})
        if matches:
            return self._format_product_match(matches[0])

        return None

    def _format_product_match(self, raw_prod: Dict[str, Any]) -> Dict[str, Any]:
        """Extrae los IDs de las tuplas Many2one para simplificar el uso."""
        uom_raw = raw_prod.get('uom_id')
        tmpl_raw = raw_prod.get('product_tmpl_id')
        return {
            'id': raw_prod['id'],
            'name': raw_prod['name'],
            'uom_id': uom_raw[0] if isinstance(uom_raw, (list, tuple)) else uom_raw,
            'uom_name': uom_raw[1] if isinstance(uom_raw, (list, tuple)) else "",
            'product_tmpl_id': tmpl_raw[0] if isinstance(tmpl_raw, (list, tuple)) else tmpl_raw
        }

    def create_product(self, name: str, default_code: str, detailed_type: str = 'product', 
                       purchase_tax_ids: Optional[List[int]] = None, vendor_id: Optional[int] = None, 
                       vendor_price: float = 0.0, vendor_code: Optional[str] = None) -> int:
        """
        Crea un nuevo producto en Odoo (vía product.template).
        Auto-asocia el proveedor y los impuestos por defecto.
        Retorna el ID del product.product variante auto-creado.
        """
        vals: Dict[str, Any] = {
            'name': name.strip(),
            'detailed_type': detailed_type,
            'default_code': default_code.strip() if default_code else False,
            'list_price': vendor_price,  # Usar precio de compra como precio base provisional
        }

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
