import unittest
from modules.buying_intelligence import (
    build_product_sales_map,
    classify_essential_products,
    determine_purchase_status,
    compute_purchase_plan,
    compute_manual_entry
)

class TestBuyingIntelligence(unittest.TestCase):
    def setUp(self):
        self.raw_lines = [
            {"product_id": [1, "Clavo"], "product_uom_qty": 100, "date_order": "2026-01-15 10:00:00", "default_code": "CLV-1"},
            {"product_id": [1, "Clavo"], "product_uom_qty": 150, "date_order": "2026-01-20 10:00:00", "default_code": "CLV-1"},
            {"product_id": [1, "Clavo"], "product_uom_qty": 200, "date_order": "2026-02-15 10:00:00", "default_code": "CLV-1"},
            {"product_id": [2, "Tornillo"], "product_uom_qty": 50, "date_order": "2026-01-15 10:00:00", "default_code": "TRN-1"},
        ]

    def test_build_sales_map_basic(self):
        sales_map = build_product_sales_map(self.raw_lines)
        self.assertIn(1, sales_map)
        self.assertIn(2, sales_map)
        
        self.assertEqual(sales_map[1]["total_qty_vendida"], 450.0)
        self.assertEqual(sales_map[1]["n_meses"], 2)
        self.assertEqual(sales_map[1]["promedio_mensual"], 225.0)
        
        self.assertEqual(sales_map[2]["total_qty_vendida"], 50.0)
        self.assertEqual(sales_map[2]["n_meses"], 1)

    def test_classify_presencia_minima(self):
        sales_map = build_product_sales_map(self.raw_lines)
        # Testing with 3 months range. Product 1 is in 2 months (66%). Product 2 is in 1 month (33%).
        # Our threshold is 75%, so neither should be essential if we require 75%.
        # Let's adjust window to 2 months. Then Prod 1 is 100%, Prod 2 is 50%.
        essential = classify_essential_products(sales_map, 2)
        self.assertEqual(len(essential), 1)
        self.assertEqual(essential[0]["product_id"], 1)

    def test_classify_presencia_total(self):
        sales_map = build_product_sales_map(self.raw_lines)
        # Window of 1 month. Both are 100% or more.
        essential = classify_essential_products(sales_map, 1)
        self.assertEqual(len(essential), 2)
        # Should be sorted by promedio_mensual desc (Prod 1 then Prod 2)
        self.assertEqual(essential[0]["product_id"], 1)
        self.assertEqual(essential[1]["product_id"], 2)

    def test_determine_status(self):
        # < 50%
        sem, stat, urg = determine_purchase_status(40.0)
        self.assertEqual(sem, "🔴")
        self.assertEqual(urg, 3)
        
        # 50 - 90%
        sem, stat, urg = determine_purchase_status(75.0)
        self.assertEqual(sem, "🟡")
        self.assertEqual(urg, 2)
        
        # > 90%
        sem, stat, urg = determine_purchase_status(95.0)
        self.assertEqual(sem, "🟢")
        self.assertEqual(urg, 1)

    def test_compute_plan(self):
        essential = [
            {"product_id": 1, "name": "Prod1", "code": "", "promedio_mensual": 100.0, "n_meses": 3, "presencia_pct": 100.0, "clasificacion": "A"}
        ]
        stock_map = {1: {"stock": 10.0, "uom": "uds"}}
        
        # Proyeccion = 100 * 1.15 = 115
        # Comprar = 115 - 10 = 105
        # Cobertura = 10 / 115 = 8.69% -> Rojo
        plan = compute_purchase_plan(essential, stock_map)
        self.assertEqual(len(plan), 1)
        self.assertAlmostEqual(plan[0]["proyeccion_mes"], 115.0, places=2)
        self.assertAlmostEqual(plan[0]["a_comprar"], 105.0, places=2)
        self.assertEqual(plan[0]["semaforo"], "🔴")

    def test_manual_entry_semaforo(self):
        manual = {"nombre": "Man1", "stock_actual": 120.0, "promedio_mensual": 100.0}
        # proy = 115
        # stock = 120 -> cobertura > 100% -> Verde
        res = compute_manual_entry(manual)
        self.assertEqual(res["semaforo"], "🟢")
        self.assertEqual(res["a_comprar"], 0.0)

if __name__ == '__main__':
    unittest.main()
