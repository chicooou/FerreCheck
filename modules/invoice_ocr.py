"""
Módulo para la extracción de ítems de facturas de compra mediante la API de Google Gemini (Vision LLM)
utilizando solicitudes HTTP directas para evitar fallos de segmentación de Pydantic/Rust en Python 3.14.
"""

import os
import json
import re
import base64
import requests
from typing import Dict, Any, Optional
from PIL import Image
import io

def compress_image(image_bytes: bytes, max_size: int = 1600, quality: int = 85) -> bytes:
    """
    Reduce las dimensiones y comprime una imagen para optimizar el envío por la API.
    """
    try:
        img = Image.open(io.BytesIO(image_bytes))
        
        # Convertir a RGB si es necesario (ej: PNG con transparencia a JPEG)
        if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
            img = img.convert('RGB')

        # Redimensionar manteniendo ratio
        if max(img.size) > max_size:
            img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            
        out_io = io.BytesIO()
        img.save(out_io, format="JPEG", quality=quality)
        return out_io.getvalue()
    except Exception as e:
        # Si falla por cualquier motivo, retornar los bytes originales
        return image_bytes

def extract_invoice_data(image_bytes: bytes, mime_type: str) -> Dict[str, Any]:
    """
    Envía la imagen a Gemini 2.5 Flash mediante llamadas HTTP directas.
    Esto previene errores de segmentación de Pydantic v2 en entornos con Python 3.14.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        try:
            import streamlit as st
            api_key = st.secrets.get("GEMINI_API_KEY")
        except Exception:
            pass
            
    if not api_key:
        raise ValueError("GEMINI_API_KEY no configurado en las variables de entorno ni en st.secrets.")

    # Optimizar imagen antes de enviar
    optimized_bytes = compress_image(image_bytes)
    
    # Codificar a base64
    base64_image = base64.b64encode(optimized_bytes).decode('utf-8')

    system_instruction = (
        "Eres un asistente especializado en extraer datos estructurados de facturas físicas "
        "o digitales de compras para una ferretería en Guatemala.\n\n"
        "INSTRUCCIONES:\n"
        "1. Analiza la imagen y extrae el número de factura, la fecha de emisión de la factura y todas las líneas de productos o insumos.\n"
        "2. Omita subtotales, totales, impuestos o descuentos. Solo nos interesan los ítems individuales.\n"
        "3. Los precios e importes unitarios deben ser el precio neto (antes de impuestos) si es visible, "
        "de lo contrario el precio que figure por unidad.\n"
        "4. Devuelve ÚNICAMENTE un objeto JSON bien formado sin rodeos, explicaciones ni etiquetas markdown "
        "como ```json. Respeta estrictamente la estructura solicitada.\n\n"
        "ESTRUCTURA DEL JSON ESPERADO:\n"
        "{\n"
        "  \"invoice_number\": \"string o null\",\n"
        "  \"invoice_date\": \"string en formato YYYY-MM-DD o null\",\n"
        "  \"line_items\": [\n"
        "    {\n"
        "      \"description\": \"Nombre o descripción detallada del artículo\",\n"
        "      \"quantity\": float,\n"
        "      \"price_unit\": float,\n"
        "      \"supplier_code\": \"código del proveedor/fabricante o null\"\n"
        "    }\n"
        "  ]\n"
        "}"
    )

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    headers = {
        "Content-Type": "application/json"
    }

    payload = {
        "systemInstruction": {
            "parts": [
                {
                    "text": system_instruction
                }
            ]
        },
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": "Extrae los ítems de esta factura de compra en formato JSON."
                    },
                    {
                        "inlineData": {
                            "mimeType": "image/jpeg",
                            "data": base64_image
                        }
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "responseMimeType": "application/json"
        }
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        
        response_json = response.json()
        
        candidates = response_json.get("candidates", [])
        if not candidates:
            raise ValueError(f"No se encontraron candidatos en la respuesta de Gemini: {response_json}")
            
        content = candidates[0].get("content", {})
        parts = content.get("parts", [])
        if not parts:
            raise ValueError(f"No se encontraron partes de contenido en la respuesta de Gemini: {response_json}")
            
        raw_text = parts[0].get("text", "").strip()
        
        # Limpiar posibles bloques markdown sobrantes
        if raw_text.startswith("```"):
            raw_text = re.sub(r'^```(?:json)?\n', '', raw_text)
            raw_text = re.sub(r'\n```$', '', raw_text)
            raw_text = raw_text.strip()

        # Parsear JSON
        data = json.loads(raw_text)
        return data

    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Error al llamar a la API de Gemini mediante HTTP: {str(e)}")
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        raise ValueError(f"Error al procesar la respuesta de Gemini: {str(e)}")
