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

    def test_classify_dual_criteria(self):
        # Queremos probar múltiples candidatos:
        # P1: pres=100% (12m/12m), vol=100 (Alta Rotación si supera percentil)
        # P2: pres=100% (12m/12m), vol=10 (Bajo volumen, debería ser Rotación Media)
        # P3: pres=80% (9m/12m), vol=200 (Alta presencia pero < 90%, debería ser Rotación Media)
        # P4: pres=50% (6m/12m), vol=500 (No es candidato, <75% presencia)
        
        # Simulamos un sales_map ya estructurado
        sales_map = {
            1: {"name": "P1", "code": "1", "promedio_mensual": 100.0, "n_meses": 12},
            2: {"name": "P2", "code": "2", "promedio_mensual": 10.0, "n_meses": 12},
            3: {"name": "P3", "code": "3", "promedio_mensual": 200.0, "n_meses": 9},
            4: {"name": "P4", "code": "4", "promedio_mensual": 500.0, "n_meses": 6},
        }
        
        # Candidates: P1, P2, P3. (P4 excluded because 6/12 = 50% < 75%)
        # Candidates promedios: [10.0, 100.0, 200.0]
        # P70 of [10.0, 100.0, 200.0] is:
        # sorted: [10, 100, 200]. len = 3. k = 2 * 0.7 = 1.4.
        # f = 1, c = 2. p70_val = 100 * 0.6 + 200 * 0.4 = 140.0
        # P1: pres=100% >= 90%, vol=100 < 140 -> Rotación Media (no supera P70)
        # P2: pres=100% >= 90%, vol=10 < 140 -> Rotación Media (no supera P70)
        # P3: pres=9/12 = 75% < 90% -> Rotación Media (no cumple presencia de Alta)
        # En este escenario particular, nadie tiene >= 90% Y >= 140 (sólo P3 tiene >=140 pero no tiene presencia >=90%).
        
        essential = classify_essential_products(sales_map, 12)
        # P4 queda fuera, quedan 3
        self.assertEqual(len(essential), 3)
        self.assertTrue(all(p["clasificacion"] == "Rotación Media" for p in essential))
        
        # Hagamos otro escenario donde alguien califica como Alta Rotación:
        # P1: pres=100%, vol=300
        # P2: pres=100%, vol=100
        # P3: pres=80%, vol=200
        sales_map_2 = {
            1: {"name": "P1", "code": "1", "promedio_mensual": 300.0, "n_meses": 12},
            2: {"name": "P2", "code": "2", "promedio_mensual": 100.0, "n_meses": 12},
            3: {"name": "P3", "code": "3", "promedio_mensual": 200.0, "n_meses": 10},
        }
        # Candidates: P1, P2, P3 (all >=75%).
        # promedios sorted: [100.0, 200.0, 300.0]. len=3. k=1.4. p70_val = 200 * 0.6 + 300 * 0.4 = 240.0.
        # P1: pres=100% >= 90%, vol=300 >= 240 -> Alta Rotación
        # P2: pres=100% >= 90%, vol=100 < 240 -> Rotación Media
        # P3: pres=10/12 = 83.3% < 90% -> Rotación Media
        
        essential_2 = classify_essential_products(sales_map_2, 12)
        self.assertEqual(len(essential_2), 3)
        
        # P1 (id 1) debe ser Alta Rotación
        p1 = next(p for p in essential_2 if p["product_id"] == 1)
        self.assertEqual(p1["clasificacion"], "Alta Rotación")
        
        # P2 y P3 deben ser Rotación Media
        p2 = next(p for p in essential_2 if p["product_id"] == 2)
        p3 = next(p for p in essential_2 if p["product_id"] == 3)
        self.assertEqual(p2["clasificacion"], "Rotación Media")
        self.assertEqual(p3["clasificacion"], "Rotación Media")

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
