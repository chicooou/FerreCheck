import unittest
import os
import json
import shutil
from modules.rules_matrix import (
    load_rules,
    save_rules,
    find_matching_rule,
    create_or_update_split_rule,
    RULES_FILE_PATH
)

class TestRulesSplit(unittest.TestCase):
    def setUp(self):
        # Hacer copia de seguridad del archivo de reglas si existe
        self.backup_path = RULES_FILE_PATH + ".bak"
        if os.path.exists(RULES_FILE_PATH):
            shutil.copyfile(RULES_FILE_PATH, self.backup_path)
            os.remove(RULES_FILE_PATH)
        else:
            self.backup_path = None

    def tearDown(self):
        # Restaurar copia de seguridad
        if os.path.exists(RULES_FILE_PATH):
            os.remove(RULES_FILE_PATH)
        if self.backup_path and os.path.exists(self.backup_path):
            shutil.copyfile(self.backup_path, RULES_FILE_PATH)
            os.remove(self.backup_path)

    def test_create_and_find_split_rule(self):
        vendor_id = 99
        vendor_name = "Proveedor De Cables"
        original_desc = "Cable con Forro Coaxial"
        
        split_products = [
            {
                "odoo_product_id": 101,
                "odoo_name": "Cable Coaxial RG6",
                "odoo_default_code": "CAB-COAX",
                "quantity_multiplier": 1.0,
                "cost_share": 0.65
            },
            {
                "odoo_product_id": 102,
                "odoo_name": "Forro Protector Negro",
                "odoo_default_code": "FOR-PROT",
                "quantity_multiplier": 2.0,
                "cost_share": 0.35
            }
        ]

        # 1. Crear la regla de split
        rule = create_or_update_split_rule(
            vendor_id=vendor_id,
            vendor_name=vendor_name,
            original_description=original_desc,
            split_products=split_products
        )
        
        self.assertEqual(rule["rule_type"], "split")
        self.assertEqual(len(rule["split_products"]), 2)
        self.assertEqual(rule["split_products"][0]["odoo_product_id"], 101)
        self.assertEqual(rule["split_products"][1]["quantity_multiplier"], 2.0)
        self.assertEqual(rule["split_products"][1]["cost_share"], 0.35)

        # 2. Buscar por coincidencia exacta
        matched = find_matching_rule(vendor_id, "Cable con Forro Coaxial")
        self.assertIsNotNone(matched)
        self.assertEqual(matched["rule_type"], "split")
        self.assertEqual(len(matched["split_products"]), 2)

        # 3. Buscar por coincidencia difusa (fuzzy)
        matched_fuzzy = find_matching_rule(vendor_id, "Cable con Forro Coaxial RG6")
        self.assertIsNotNone(matched_fuzzy)
        self.assertEqual(matched_fuzzy["id"], rule["id"])
