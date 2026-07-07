"""
Módulo de Inteligencia de Compras — Productos Esenciales
Analiza el historial de ventas y stock para determinar requerimientos de compra.
"""

import json
import os
import datetime
from typing import List, Dict, Any, Tuple
from dateutil.relativedelta import relativedelta

CACHE_FILE = os.path.join("data", "essential_products_cache.json")
MANUAL_FILE = os.path.join("data", "manual_essential_products.json")

UMBRAL_CRITICO = 0.50
UMBRAL_ALERTA = 0.90
FACTOR_SEGURIDAD = 1.15
MIN_PRESENCIA_FRACCION = 0.75

def build_product_sales_map(raw_lines: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    """
    Agrupa las líneas crudas de Odoo por producto y calcula estadísticas mensuales.
    """
    sales_map = {}
    
    for line in raw_lines:
        prod_tuple = line.get('product_id')
        if not prod_tuple or not isinstance(prod_tuple, list):
            continue
            
        prod_id = prod_tuple[0]
        prod_name = prod_tuple[1]
        
        date_order_str = line.get('date_order')
        if not date_order_str:
            continue
            
        # Odoo dates are string 'YYYY-MM-DD HH:MM:SS'
        try:
            dt = datetime.datetime.strptime(date_order_str, '%Y-%m-%d %H:%M:%S')
            year_month = f"{dt.year}-{dt.month:02d}"
            ym_tuple = (dt.year, dt.month)
        except ValueError:
            continue
            
        qty = float(line.get('product_uom_qty', 0.0))
        default_code = line.get('default_code', '')
        
        if prod_id not in sales_map:
            sales_map[prod_id] = {
                "name": prod_name,
                "code": default_code,
                "total_qty_vendida": 0.0,
                "meses_presentes_set": set(),
                "qty_por_mes": {}
            }
            
        sm = sales_map[prod_id]
        sm["total_qty_vendida"] += qty
        sm["meses_presentes_set"].add(ym_tuple)
        
        if year_month not in sm["qty_por_mes"]:
            sm["qty_por_mes"][year_month] = 0.0
        sm["qty_por_mes"][year_month] += qty

    # Transformar sets a listas y calcular promedios
    for prod_id, sm in sales_map.items():
        sm["meses_presentes"] = sorted(list(sm["meses_presentes_set"]))
        sm["n_meses"] = len(sm["meses_presentes"])
        if sm["n_meses"] > 0:
            sm["promedio_mensual"] = sm["total_qty_vendida"] / sm["n_meses"]
        else:
            sm["promedio_mensual"] = 0.0
        del sm["meses_presentes_set"]
        
    return sales_map

def classify_essential_products(sales_map: Dict[int, Dict[str, Any]], total_months_in_range: int) -> List[Dict[str, Any]]:
    """
    Filtra los productos que aparecen consistentemente y los clasifica.
    """
    if total_months_in_range <= 0:
        total_months_in_range = 1
        
    essential = []
    
    for prod_id, sm in sales_map.items():
        presencia_fraccion = sm["n_meses"] / total_months_in_range
        if presencia_fraccion >= MIN_PRESENCIA_FRACCION:
            essential.append({
                "product_id": prod_id,
                "name": sm["name"],
                "code": sm["code"],
                "promedio_mensual": sm["promedio_mensual"],
                "n_meses": sm["n_meses"],
                "presencia_pct": presencia_fraccion * 100.0
            })
            
    # Ordenar por promedio mensual descendente
    essential.sort(key=lambda x: x["promedio_mensual"], reverse=True)
    
    # Clasificación Top 20%
    num_top = max(1, int(len(essential) * 0.20))
    for i, prod in enumerate(essential):
        if i < num_top:
            prod["clasificacion"] = "Alta Rotación"
        else:
            prod["clasificacion"] = "Rotación Media"
            
    return essential

def determine_purchase_status(cobertura_pct: float) -> Tuple[str, str, int]:
    """Retorna (semaforo, status, urgencia)"""
    if cobertura_pct < UMBRAL_CRITICO * 100:
        return "🔴", "🔴 Comprar Ya", 3
    elif cobertura_pct < UMBRAL_ALERTA * 100:
        return "🟡", "🟡 Reponer Pronto", 2
    else:
        return "🟢", "🟢 OK", 1

def compute_purchase_plan(essential_products: List[Dict[str, Any]], stock_map: Dict[int, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Calcula el plan de compra cruzando ventas con stock actual.
    """
    plan = []
    
    for prod in essential_products:
        prod_id = prod["product_id"]
        stock_info = stock_map.get(prod_id, {})
        stock_actual = stock_info.get("stock", 0.0)
        uom = stock_info.get("uom", "Unidades")
        
        proyeccion_mes = prod["promedio_mensual"] * FACTOR_SEGURIDAD
        a_comprar = max(0.0, proyeccion_mes - stock_actual)
        
        if proyeccion_mes > 0:
            cobertura_pct = (stock_actual / proyeccion_mes) * 100.0
        else:
            cobertura_pct = 100.0 # Si no proyectamos vender nada, estamos cubiertos
            
        semaforo, status, urgencia = determine_purchase_status(cobertura_pct)
        
        plan.append({
            "product_id": prod_id,
            "semaforo": semaforo,
            "status": status,
            "urgencia": urgencia,
            "nombre": prod["name"],
            "codigo": prod["code"],
            "stock_actual": stock_actual,
            "uom": uom,
            "promedio_mensual": prod["promedio_mensual"],
            "proyeccion_mes": proyeccion_mes,
            "a_comprar": a_comprar,
            "cobertura_pct": cobertura_pct,
            "clasificacion": prod["clasificacion"],
            "n_meses": prod["n_meses"],
            "presencia_pct": prod["presencia_pct"],
            "fuente": "odoo"
        })
        
    # Ordenar por urgencia descendente (rojo primero), luego por a_comprar descendente
    plan.sort(key=lambda x: (x["urgencia"], x["a_comprar"]), reverse=True)
    return plan

def run_full_analysis(odoo_client, months_window: int = 12) -> List[Dict[str, Any]]:
    """
    Orquesta el flujo completo obteniendo datos de Odoo.
    """
    # 1. Obtener historial de ventas
    raw_lines = odoo_client.fetch_sales_history_by_product(months=months_window)
    
    # 2. Construir mapa de ventas y clasificar
    sales_map = build_product_sales_map(raw_lines)
    essential = classify_essential_products(sales_map, total_months_in_range=months_window)
    
    # 3. Obtener stock
    product_ids = [p["product_id"] for p in essential]
    stock_map = odoo_client.fetch_products_stock(product_ids)
    
    # 4. Calcular plan
    plan = compute_purchase_plan(essential, stock_map)
    
    # 5. Guardar en caché
    save_analysis_cache(plan, months_window)
    return plan

def save_analysis_cache(plan: List[Dict[str, Any]], months_window: int):
    """Guarda el último análisis en cache."""
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    payload = {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "months_window": months_window,
        "products": plan
    }
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

def load_analysis_cache() -> Tuple[List[Dict[str, Any]], str, int]:
    """Carga el cache. Retorna (plan, timestamp, months_window)."""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                payload = json.load(f)
                return payload.get("products", []), payload.get("timestamp"), payload.get("months_window", 12)
        except Exception:
            pass
    return [], "", 12

def save_manual_products(products: List[Dict[str, Any]]):
    """Guarda productos manuales."""
    os.makedirs(os.path.dirname(MANUAL_FILE), exist_ok=True)
    try:
        with open(MANUAL_FILE, "w", encoding="utf-8") as f:
            json.dump(products, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

def load_manual_products() -> List[Dict[str, Any]]:
    """Carga productos manuales."""
    if os.path.exists(MANUAL_FILE):
        try:
            with open(MANUAL_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def compute_manual_entry(product: Dict[str, Any]) -> Dict[str, Any]:
    """
    Toma un producto manual (con stock_actual y promedio_mensual)
    y le aplica la lógica de semáforo.
    """
    proyeccion_mes = product.get("promedio_mensual", 0.0) * FACTOR_SEGURIDAD
    stock_actual = product.get("stock_actual", 0.0)
    a_comprar = max(0.0, proyeccion_mes - stock_actual)
    
    if proyeccion_mes > 0:
        cobertura_pct = (stock_actual / proyeccion_mes) * 100.0
    else:
        cobertura_pct = 100.0
        
    semaforo, status, urgencia = determine_purchase_status(cobertura_pct)
    
    res = product.copy()
    res.update({
        "semaforo": semaforo,
        "status": status,
        "urgencia": urgencia,
        "proyeccion_mes": proyeccion_mes,
        "a_comprar": a_comprar,
        "cobertura_pct": cobertura_pct,
        "fuente": "manual"
    })
    return res
