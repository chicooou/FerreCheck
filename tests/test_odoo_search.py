import unittest
from unittest.mock import MagicMock, patch
from modules.odoo_connector import OdooRPC

class TestOdooSearch(unittest.TestCase):
    def setUp(self):
        self.client = OdooRPC("http://localhost:8069", "test_db", "admin", "secret")
        self.client._execute = MagicMock()

    def test_find_product_by_code_empty(self):
        # Si el código es vacío o None, debe retornar None inmediatamente sin ejecutar llamadas RPC
        res = self.client.find_product_by_code("")
        self.assertIsNone(res)
        self.client._execute.assert_not_called()

    def test_find_product_by_code_default_code_match(self):
        # Simular que encuentra un match en la primera consulta (default_code)
        self.client._execute.return_value = [{
            "id": 42,
            "name": "Clavo de 2 pulgadas",
            "uom_id": [1, "Unidades"],
            "product_tmpl_id": [10, "Clavo de 2 pulgadas template"],
            "list_price": 5.5,
            "default_code": "CLV-02"
        }]

        res = self.client.find_product_by_code("CLV-02")
        self.assertIsNotNone(res)
        self.assertEqual(res["id"], 42)
        self.assertEqual(res["default_code"], "CLV-02")
        
        # Debe haber ejecutado search_read en product.product buscando por default_code
        self.client._execute.assert_called_once()
        args = self.client._execute.call_args[0]
        self.assertEqual(args[0], 'product.product')
        self.assertEqual(args[1], 'search_read')
        self.assertIn(('default_code', '=', 'CLV-02'), args[2][0])

    def test_find_product_by_code_barcode_match(self):
        # Primera consulta (default_code) no retorna nada, segunda consulta (barcode) retorna el match
        self.client._execute.side_effect = [
            [], # default_code search
            [{  # barcode search
                "id": 99,
                "name": "Martillo Premium",
                "uom_id": [1, "Unidades"],
                "product_tmpl_id": [20, "Martillo Premium template"],
                "list_price": 75.0,
                "default_code": "MRT-01"
            }]
        ]

        res = self.client.find_product_by_code("74010101")
        self.assertIsNotNone(res)
        self.assertEqual(res["id"], 99)
        self.assertEqual(res["default_code"], "MRT-01")
        
        # Debió haber llamado a _execute dos veces
        self.assertEqual(self.client._execute.call_count, 2)
        
        # La primera llamada debió ser para default_code
        first_args = self.client._execute.call_args_list[0][0]
        self.assertIn(('default_code', '=', '74010101'), first_args[2][0])
        
        # La segunda llamada debió ser para barcode
        second_args = self.client._execute.call_args_list[1][0]
        self.assertIn(('barcode', '=', '74010101'), second_args[2][0])

    def test_find_product_by_code_supplier_match(self):
        # default_code vacio, barcode vacio, y encuentra en product.supplierinfo
        self.client._execute.side_effect = [
            [], # default_code search
            [], # barcode search
            [{'product_tmpl_id': [30, "Template 30"]}], # supplierinfo search
            [{  # product.product search
                "id": 150,
                "name": "Pala Metálica",
                "uom_id": [1, "Unidades"],
                "product_tmpl_id": [30, "Pala Metálica template"],
                "list_price": 45.0,
                "default_code": "PAL-M"
            }]
        ]

        res = self.client.find_product_by_code("SUPP-CODE-123", vendor_id=5)
        self.assertIsNotNone(res)
        self.assertEqual(res["id"], 150)
        self.assertEqual(res["default_code"], "PAL-M")
        
        # Debe haber ejecutado 4 llamadas
        self.assertEqual(self.client._execute.call_count, 4)

        # La tercera llamada debió buscar en product.supplierinfo
        third_args = self.client._execute.call_args_list[2][0]
        self.assertEqual(third_args[0], 'product.supplierinfo')
        self.assertIn(('partner_id', '=', 5), third_args[2][0])
        self.assertIn(('product_code', '=', 'SUPP-CODE-123'), third_args[2][0])

    def test_search_product_by_tokens_and(self):
        # 1. default_code search: vacio
        # 2. supplierinfo search: vacio
        # 3. exact name match (ilike "Clavo Acero 2"): vacio
        # 4. token-based name search (AND of significant words): encuentra match
        self.client._execute.side_effect = [
            [], # default_code
            [], # exact name match (ilike "Clavo de Acero de 2 pulgadas")
            [{  # token-based match (AND of ['pulgadas', 'acero', 'clavo'])
                "id": 88,
                "name": "Clavo Acero 2",
                "uom_id": [1, "Unidades"],
                "product_tmpl_id": [8, "Clavo Acero 2 template"],
                "list_price": 10.0,
                "default_code": "CLV-A2"
            }]
        ]

        res = self.client.search_product("Clavo de Acero de 2 pulgadas")
        self.assertIsNotNone(res)
        self.assertEqual(res["id"], 88)
        self.assertEqual(res["default_code"], "CLV-A2")
        
        # Debió haber llamado a _execute 3 veces (default_code, exact name, token AND)
        self.assertEqual(self.client._execute.call_count, 3)
        
        # Verificar la llamada del AND
        and_call_args = self.client._execute.call_args_list[2][0]
        self.assertEqual(and_call_args[0], 'product.product')
        self.assertEqual(and_call_args[1], 'search_read')
        # Las palabras significativas ordenadas por longitud: 'pulgadas', 'acero', 'clavo' (de >=3 chars y no stop-words)
        domain = and_call_args[2][0]
        self.assertIn(('name', 'ilike', 'pulgadas'), domain)
        self.assertIn(('name', 'ilike', 'acero'), domain)
        self.assertIn(('name', 'ilike', 'clavo'), domain)

    def test_search_product_by_tokens_top_2(self):
        # default_code search: vacio
        # exact name match: vacio
        # token AND match: vacio
        # token top_2 match: encuentra match
        self.client._execute.side_effect = [
            [], # default_code
            [], # exact name match
            [], # token AND match
            [{  # token top_2 match (using longest words: 'cemento', 'tolteca')
                "id": 202,
                "name": "Cemento Gris Tolteca 50kg",
                "uom_id": [1, "Sacos"],
                "product_tmpl_id": [12, "Cemento template"],
                "list_price": 85.0,
                "default_code": "CEM-GT"
            }]
        ]

        # "de" y "y" son stopwords, "tolteca" (7), "cemento" (7), "gris" (4) son significativas
        res = self.client.search_product("Cemento de Gris y Tolteca")
        self.assertIsNotNone(res)
        self.assertEqual(res["id"], 202)
        self.assertEqual(res["default_code"], "CEM-GT")

        self.assertEqual(self.client._execute.call_count, 4)
        
        # La última llamada usa solo las 2 palabras más largas ('cemento', 'tolteca')
        top_2_call_args = self.client._execute.call_args_list[3][0]
        domain = top_2_call_args[2][0]
        self.assertEqual(len(domain), 2)
        self.assertIn(('name', 'ilike', 'cemento'), domain)
        self.assertIn(('name', 'ilike', 'tolteca'), domain)

