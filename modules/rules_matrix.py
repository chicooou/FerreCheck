"""
Módulo para el manejo y persistencia de la matriz de reglas de conversión locales.
Guarda las preferencias del usuario para convertir descripciones de facturas a productos de Odoo.
"""

import os
import json
import uuid
import datetime
import difflib
from typing import List, Dict, Any, Optional

RULES_FILE_PATH = os.path.join("data", "rules_matrix.json")

def load_rules() -> List[Dict[str, Any]]:
    """Carga las reglas de conversión desde el archivo JSON local."""
    if not os.path.exists(RULES_FILE_PATH):
        # Asegurar que el directorio data exista
        os.makedirs(os.path.dirname(RULES_FILE_PATH), exist_ok=True)
        save_rules([])
        return []
    
    try:
        with open(RULES_FILE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("rules", [])
    except Exception:
        return []

def save_rules(rules: List[Dict[str, Any]]) -> None:
    """Guarda las reglas de conversión en el archivo JSON local."""
    os.makedirs(os.path.dirname(RULES_FILE_PATH), exist_ok=True)
    with open(RULES_FILE_PATH, "w", encoding="utf-8") as f:
        json.dump({"rules": rules}, f, indent=4, ensure_ascii=False)

def find_matching_rule(vendor_id: int, original_description: str, threshold: float = 0.75) -> Optional[Dict[str, Any]]:
    """
    Busca una regla coincidente usando similaridad de string (fuzzy match) para el proveedor dado.
    """
    rules = load_rules()
    best_match = None
    highest_ratio = 0.0

    orig_clean = original_description.strip().lower()

    for rule in rules:
        if rule.get("vendor_id") == vendor_id:
            rule_desc = rule.get("original_description", "").strip().lower()
            
            # Comparación exacta primero
            if orig_clean == rule_desc:
                return rule
            
            # Comparación difusa
            ratio = difflib.SequenceMatcher(None, orig_clean, rule_desc).ratio()
            if ratio >= threshold and ratio > highest_ratio:
                highest_ratio = ratio
                best_match = rule

    return best_match

def create_or_update_rule(vendor_id: int, vendor_name: str, original_description: str,
                          converted_description: str, quantity_multiplier: float,
                          odoo_product_id: int, odoo_default_code: str) -> Dict[str, Any]:
    """
    Crea una nueva regla o actualiza una existente si coincide exactamente la descripción original.
    """
    rules = load_rules()
    orig_clean = original_description.strip()
    
    existing_rule = None
    for r in rules:
        if r.get("vendor_id") == vendor_id and r.get("original_description", "").strip().lower() == orig_clean.lower():
            existing_rule = r
            break

    now_str = datetime.datetime.now().isoformat()

    if existing_rule:
        existing_rule["converted_description"] = converted_description
        existing_rule["quantity_multiplier"] = float(quantity_multiplier)
        existing_rule["odoo_product_id"] = odoo_product_id
        existing_rule["odoo_default_code"] = odoo_default_code
        existing_rule["last_used"] = now_str
        existing_rule["use_count"] = existing_rule.get("use_count", 0) + 1
        rule_to_return = existing_rule
    else:
        new_rule = {
            "id": str(uuid.uuid4()),
            "vendor_id": vendor_id,
            "vendor_name": vendor_name,
            "original_description": orig_clean,
            "converted_description": converted_description,
            "quantity_multiplier": float(quantity_multiplier),
            "odoo_product_id": odoo_product_id,
            "odoo_default_code": odoo_default_code,
            "created_at": now_str,
            "last_used": now_str,
            "use_count": 1
        }
        rules.append(new_rule)
        rule_to_return = new_rule

    save_rules(rules)
    return rule_to_return
