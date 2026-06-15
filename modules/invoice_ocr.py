"""
Módulo para la extracción de ítems de facturas de compra mediante la API de Google Gemini (Vision LLM).
"""

import os
import json
import re
from typing import Dict, Any, Optional
from PIL import Image
import io
from google import genai
from google.genai import types

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
    Envía la imagen a Gemini 2.5 Flash para extraer los ítems y número de factura en JSON.
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

    # Inicializar cliente Gemini
    client = genai.Client(api_key=api_key)

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

    try:
        # Cargar parte de imagen
        image_part = types.Part.from_bytes(
            data=optimized_bytes,
            mime_type="image/jpeg" # Convertido a JPEG durante optimización
        )

        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[
                image_part,
                "Extrae los ítems de esta factura de compra en formato JSON."
            ],
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.1,
                response_mime_type="application/json"
            )
        )

        raw_text = response.text.strip()
        
        # Limpiar posibles bloques markdown sobrantes
        if raw_text.startswith("```"):
            # Remover ```json del inicio y ``` del final
            raw_text = re.sub(r'^```(?:json)?\n', '', raw_text)
            raw_text = re.sub(r'\n```$', '', raw_text)
            raw_text = raw_text.strip()

        # Parsear JSON
        data = json.loads(raw_text)
        return data

    except json.JSONDecodeError as e:
        raise ValueError(f"La IA retornó una respuesta que no es JSON válido: {e}. Respuesta: {response.text}")
    except Exception as e:
        raise RuntimeError(f"Error al llamar a la API de Gemini: {str(e)}")
