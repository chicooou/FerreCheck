import sys
import os
import datetime

# Add the root directory of the project to PYTHONPATH
sys.path.append(os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from modules.engine import (
    calcular_utilidad_por_modalidad,
    calcular_proyeccion_futura,
    evaluar_madurez_historial
)

def run_tests():
    print("Iniciando pruebas unitarias para Semáforos Predictivos (TDD)...")
    
    # ---------------------------------------------------------
    # Escenario 1: Solo Contado
    # ---------------------------------------------------------
    print("Test 1: Solo Contado...")
    compras_1 = [
        {"monto": 5000.0, "fecha": "2026-05-10", "modalidad": "Contado", "proveedor": "ProvA"},
        {"monto": 5000.0, "fecha": "2026-05-15", "modalidad": "Contado", "proveedor": "ProvB"},
        {"monto": 5000.0, "fecha": "2026-05-20", "modalidad": "Contado", "proveedor": "ProvC"}
    ]
    util_1 = calcular_utilidad_por_modalidad(
        ventas=120000.0,
        gastos_totales=20000.0,
        compras=compras_1,
        deudas_heredadas=[],
        mes_actual=5,
        ano_actual=2026
    )
    
    # Check that compromisos are 0
    assert util_1.get("compromisos_mes_siguiente", 0.0) == 0.0
    assert util_1.get("compromisos_mes_2", 0.0) == 0.0
    
    proy_1 = calcular_proyeccion_futura(
        util_modalidad=util_1,
        deudas_futuras=[],
        ventas_diarias=[],
        ventas_sidebar=120000.0,
        gastos={"renta": 10000.0, "planilla": 10000.0},
        estrategia="balance",
        mes_actual=5,
        ano_actual=2026
    )
    
    assert proy_1["mes_1"]["comprometido"] == 0.0
    assert proy_1["mes_2"]["comprometido"] == 0.0
    assert proy_1["mes_1"]["consumo_pct"] == 0.0
    assert proy_1["mes_2"]["consumo_pct"] == 0.0
    
    # ---------------------------------------------------------
    # Escenario 2: Solo Crédito 30d
    # ---------------------------------------------------------
    print("Test 2: Solo Crédito 30 días...")
    compras_2 = [
        {"monto": 10000.0, "fecha": "2026-05-15", "modalidad": "Crédito 30 días", "proveedor": "ProvA"}
    ]
    util_2 = calcular_utilidad_por_modalidad(
        ventas=120000.0,
        gastos_totales=20000.0,
        compras=compras_2,
        deudas_heredadas=[],
        mes_actual=5,
        ano_actual=2026
    )
    
    assert util_2["compromisos_mes_siguiente"] == 10000.0
    assert util_2.get("compromisos_mes_2", 0.0) == 0.0
    
    proy_2 = calcular_proyeccion_futura(
        util_modalidad=util_2,
        deudas_futuras=[],
        ventas_diarias=[],
        ventas_sidebar=120000.0,
        gastos={"renta": 10000.0, "planilla": 10000.0},
        estrategia="balance",
        mes_actual=5,
        ano_actual=2026
    )
    
    assert proy_2["mes_1"]["comprometido"] == 10000.0
    assert proy_2["mes_2"]["comprometido"] == 0.0

    # ---------------------------------------------------------
    # Escenario 3: Mix Contado + 30d + 60d
    # ---------------------------------------------------------
    print("Test 3: Mix Contado, 30d y 60d...")
    compras_3 = [
        {"monto": 3000.0, "fecha": "2026-05-10", "modalidad": "Contado", "proveedor": "ProvA"},
        {"monto": 5000.0, "fecha": "2026-05-12", "modalidad": "Crédito 30 días", "proveedor": "ProvB"},
        {"monto": 4000.0, "fecha": "2026-05-15", "modalidad": "Crédito 60 días", "proveedor": "ProvC"}
    ]
    util_3 = calcular_utilidad_por_modalidad(
        ventas=120000.0,
        gastos_totales=20000.0,
        compras=compras_3,
        deudas_heredadas=[],
        mes_actual=5,
        ano_actual=2026
    )
    
    assert util_3["compromisos_mes_siguiente"] == 5000.0
    assert util_3.get("compromisos_mes_2", 0.0) == 4000.0
    
    proy_3 = calcular_proyeccion_futura(
        util_modalidad=util_3,
        deudas_futuras=[],
        ventas_diarias=[],
        ventas_sidebar=120000.0,
        gastos={"renta": 10000.0, "planilla": 10000.0},
        estrategia="balance",
        mes_actual=5,
        ano_actual=2026
    )
    assert proy_3["mes_1"]["comprometido"] == 5000.0
    assert proy_3["mes_2"]["comprometido"] == 4000.0

    # ---------------------------------------------------------
    # Escenario 4: Crédito 45d cruzando mes
    # 20 de Mayo + 45 días = 4 de Julio. 
    # Distancia en meses desde Mayo (mes 5) a Julio (mes 7) = 2 meses (Mes+2).
    # ---------------------------------------------------------
    print("Test 4: Crédito 45 días cruzando mes...")
    compras_4 = [
        {"monto": 8000.0, "fecha": "2026-05-20", "modalidad": "Crédito 45 días", "proveedor": "ProvA"}
    ]
    util_4 = calcular_utilidad_por_modalidad(
        ventas=120000.0,
        gastos_totales=20000.0,
        compras=compras_4,
        deudas_heredadas=[],
        mes_actual=5,
        ano_actual=2026
    )
    assert util_4["compromisos_mes_siguiente"] == 0.0
    assert util_4.get("compromisos_mes_2", 0.0) == 8000.0
    
    proy_4 = calcular_proyeccion_futura(
        util_modalidad=util_4,
        deudas_futuras=[],
        ventas_diarias=[],
        ventas_sidebar=120000.0,
        gastos={"renta": 10000.0, "planilla": 10000.0},
        estrategia="balance",
        mes_actual=5,
        ano_actual=2026
    )
    assert proy_4["mes_1"]["comprometido"] == 0.0
    assert proy_4["mes_2"]["comprometido"] == 8000.0

    # ---------------------------------------------------------
    # Escenario 5: Crédito 45d inicio de mes
    # 1 de Mayo + 45 días = 15 de Junio.
    # Distancia en meses desde Mayo (mes 5) a Junio (mes 6) = 1 mes (Mes+1).
    # ---------------------------------------------------------
    print("Test 5: Crédito 45 días inicio de mes...")
    compras_5 = [
        {"monto": 8000.0, "fecha": "2026-05-01", "modalidad": "Crédito 45 días", "proveedor": "ProvA"}
    ]
    util_5 = calcular_utilidad_por_modalidad(
        ventas=120000.0,
        gastos_totales=20000.0,
        compras=compras_5,
        deudas_heredadas=[],
        mes_actual=5,
        ano_actual=2026
    )
    assert util_5["compromisos_mes_siguiente"] == 8000.0
    assert util_5.get("compromisos_mes_2", 0.0) == 0.0
    
    proy_5 = calcular_proyeccion_futura(
        util_modalidad=util_5,
        deudas_futuras=[],
        ventas_diarias=[],
        ventas_sidebar=120000.0,
        gastos={"renta": 10000.0, "planilla": 10000.0},
        estrategia="balance",
        mes_actual=5,
        ano_actual=2026
    )
    assert proy_5["mes_1"]["comprometido"] == 8000.0
    assert proy_5["mes_2"]["comprometido"] == 0.0

    # ---------------------------------------------------------
    # Escenario 6: Deudas futuras en cola
    # deudas_futuras con vencimiento en Mes+1 y Mes+2 heredadas.
    # ---------------------------------------------------------
    print("Test 6: Deudas futuras en cola...")
    deudas_futuras_cola = [
        {
            "id": "abc-123",
            "monto": 3000.0,
            "proveedor": "ProvCola1",
            "mes_vencimiento": 6,
            "ano_vencimiento": 2026,
            "modalidad_original": "Crédito 60 días"
        },
        {
            "id": "xyz-789",
            "monto": 4000.0,
            "proveedor": "ProvCola2",
            "mes_vencimiento": 7,
            "ano_vencimiento": 2026,
            "modalidad_original": "Crédito 60 días"
        }
    ]
    util_6 = calcular_utilidad_por_modalidad(
        ventas=120000.0,
        gastos_totales=20000.0,
        compras=[],
        deudas_heredadas=[],
        mes_actual=5,
        ano_actual=2026
    )
    proy_6 = calcular_proyeccion_futura(
        util_modalidad=util_6,
        deudas_futuras=deudas_futuras_cola,
        ventas_diarias=[],
        ventas_sidebar=120000.0,
        gastos={"renta": 10000.0, "planilla": 10000.0},
        estrategia="balance",
        mes_actual=5,
        ano_actual=2026
    )
    assert proy_6["mes_1"]["comprometido"] == 3000.0
    assert proy_6["mes_2"]["comprometido"] == 4000.0

    # ---------------------------------------------------------
    # Escenario 7: Sobrepaso límite futuro
    # límite es Q14,300 (balance), si comprometido = Q15,000 → >90% (rojo)
    # ---------------------------------------------------------
    print("Test 7: Sobrepaso de límite futuro (color de semáforo)...")
    compras_7 = [
        {"monto": 15000.0, "fecha": "2026-05-10", "modalidad": "Crédito 30 días", "proveedor": "ProvA"}
    ]
    util_7 = calcular_utilidad_por_modalidad(
        ventas=120000.0,
        gastos_totales=20000.0,
        compras=compras_7,
        deudas_heredadas=[],
        mes_actual=5,
        ano_actual=2026
    )
    proy_7 = calcular_proyeccion_futura(
        util_modalidad=util_7,
        deudas_futuras=[],
        ventas_diarias=[],
        ventas_sidebar=100000.0,
        gastos={"renta": 90000.0},
        estrategia="balance",
        mes_actual=5,
        ano_actual=2026
    )
    assert proy_7["mes_1"]["limite_proyectado"] == 9000.0
    assert proy_7["mes_1"]["comprometido"] == 15000.0
    assert proy_7["mes_1"]["consumo_pct"] > 100.0
    assert "Rojo" in proy_7["mes_1"]["semaforo"]["color"]

    # ---------------------------------------------------------
    # Escenario 8: Cruce de año
    # Mes=Diciembre 2026, crédito 30d -> Mes+1 = Ene 2027, Mes+2 = Feb 2027
    # ---------------------------------------------------------
    print("Test 8: Cruce de año...")
    compras_8 = [
        {"monto": 5000.0, "fecha": "2026-12-15", "modalidad": "Crédito 30 días", "proveedor": "ProvA"},
        {"monto": 3000.0, "fecha": "2026-12-15", "modalidad": "Crédito 60 días", "proveedor": "ProvB"}
    ]
    util_8 = calcular_utilidad_por_modalidad(
        ventas=100000.0,
        gastos_totales=10000.0,
        compras=compras_8,
        deudas_heredadas=[],
        mes_actual=12,
        ano_actual=2026
    )
    proy_8 = calcular_proyeccion_futura(
        util_modalidad=util_8,
        deudas_futuras=[],
        ventas_diarias=[],
        ventas_sidebar=100000.0,
        gastos={"renta": 10000.0},
        estrategia="balance",
        mes_actual=12,
        ano_actual=2026
    )
    assert proy_8["mes_1"]["mes"] == 1
    assert proy_8["mes_1"]["ano"] == 2027
    assert "Enero" in proy_8["mes_1"]["nombre"]
    assert proy_8["mes_1"]["comprometido"] == 5000.0
    
    assert proy_8["mes_2"]["mes"] == 2
    assert proy_8["mes_2"]["ano"] == 2027
    assert "Febrero" in proy_8["mes_2"]["nombre"]
    assert proy_8["mes_2"]["comprometido"] == 3000.0

    # ---------------------------------------------------------
    # Escenario 9: Sin compras
    # ---------------------------------------------------------
    print("Test 9: Sin compras...")
    util_9 = calcular_utilidad_por_modalidad(
        ventas=100000.0,
        gastos_totales=10000.0,
        compras=[],
        deudas_heredadas=[],
        mes_actual=5,
        ano_actual=2026
    )
    proy_9 = calcular_proyeccion_futura(
        util_modalidad=util_9,
        deudas_futuras=[],
        ventas_diarias=[],
        ventas_sidebar=100000.0,
        gastos={"renta": 10000.0},
        estrategia="balance",
        mes_actual=5,
        ano_actual=2026
    )
    assert proy_9["mes_1"]["comprometido"] == 0.0
    assert proy_9["mes_2"]["comprometido"] == 0.0

    # ---------------------------------------------------------
    # Escenario 10: Extrapolación de Caja Diaria
    # 10 ventas de 5,000 en 10 días.
    # ---------------------------------------------------------
    print("Test 10: Extrapolación de Caja Diaria...")
    ventas_diarias = [
        {"id": f"sale-{i}", "monto": 5000.0, "fecha": f"2026-05-{i:02d}", "nota": "test"}
        for i in range(1, 11)  # 10 days of sales
    ]
    util_10 = calcular_utilidad_por_modalidad(
        ventas=100000.0,
        gastos_totales=20000.0,
        compras=[],
        deudas_heredadas=[],
        mes_actual=5,
        ano_actual=2026
    )
    proy_10 = calcular_proyeccion_futura(
        util_modalidad=util_10,
        deudas_futuras=[],
        ventas_diarias=ventas_diarias,
        ventas_sidebar=100000.0,
        gastos={"renta": 20000.0},
        estrategia="balance",
        mes_actual=5,
        ano_actual=2026
    )
    assert proy_10["metodo_proyeccion"] == "caja_diaria"
    assert abs(proy_10["ventas_proyectadas"] - 155000.0) < 0.01

    # ---------------------------------------------------------
    # Escenario 11: Evaluar Madurez de Historial (FASE 2)
    # ---------------------------------------------------------
    print("Test 11: Madurez Historial...")
    mad_1 = evaluar_madurez_historial({})
    assert mad_1["puede_usar_promedio"] is False
    
    hist_5 = {f"2026_{i}": {"ventas": 100000.0} for i in range(1, 6)}
    mad_2 = evaluar_madurez_historial(hist_5)
    assert mad_2["puede_usar_promedio"] is False
    
    hist_6 = {f"2026_{i}": {"ventas": 100000.0} for i in range(1, 7)}
    mad_3 = evaluar_madurez_historial(hist_6)
    assert mad_3["puede_usar_promedio"] is True
    assert mad_3["periodos_cerrados"] == 6

    print("\n¡TODAS LAS PRUEBAS UNITARIAS PASARON CON ÉXITO! 🎉")

if __name__ == "__main__":
    run_tests()
