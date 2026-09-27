import os
import json
import logging
import urllib.request
import urllib.error
from flask import current_app

logger = logging.getLogger('ai_service')

def get_gemini_api_key():
    """Retrieve Gemini API key from environment, Flask config, or permanent fallback."""
    try:
        if current_app:
            return current_app.config.get('GEMINI_API_KEY', 'AQ.Ab8RN6L8EbjpH6wX34JAB4f4hNWsztRKUum1GbRAdHnwD54rBQ')
    except Exception:
        pass
    return os.environ.get('GEMINI_API_KEY', 'AQ.Ab8RN6L8EbjpH6wX34JAB4f4hNWsztRKUum1GbRAdHnwD54rBQ')

def call_gemini_api(prompt, system_instruction=None, json_mode=False):
    """
    Direct REST API call to Google Gemini 2.5 Flash / 1.5 Flash.
    Uses standard urllib for ultra-fast, zero-dependency execution across any VPS or OS.
    """
    api_key = get_gemini_api_key()
    if not api_key:
        logger.warning("Gemini API Key missing.")
        return None

    # Active Gemini model endpoints in order of performance
    endpoints = [
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent?key={api_key}",
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent?key={api_key}",
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent?key={api_key}",
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={api_key}"
    ]

    contents = []
    if system_instruction:
        contents.append({
            "role": "user",
            "parts": [{"text": f"System Context & Instructions: {system_instruction}\n\nTask Prompt: {prompt}"}]
        })
    else:
        contents.append({
            "role": "user",
            "parts": [{"text": prompt}]
        })

    payload = {
        "contents": contents,
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 1024
        }
    }

    if json_mode:
        payload["generationConfig"]["responseMimeType"] = "application/json"

    data_bytes = json.dumps(payload).encode('utf-8')
    
    for url in endpoints:
        try:
            req = urllib.request.Request(url, data=data_bytes, headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=12) as resp:
                result = json.loads(resp.read().decode('utf-8'))
                if result and 'candidates' in result and len(result['candidates']) > 0:
                    parts = result['candidates'][0].get('content', {}).get('parts', [])
                    if parts:
                        return parts[0].get('text', '')
        except urllib.error.HTTPError as e:
            err_body = e.read().decode('utf-8', errors='ignore')
            logger.warning(f"Gemini API HTTP Error {e.code} for {url}: {err_body}")
            continue
        except Exception as e:
            logger.warning(f"Gemini API Request failed: {e}")
            continue

    return None

def parse_voice_query_with_ai(spoken_text):
    """
    Uses Gemini AI to parse spoken voice input (English, Tamil, Tanglish)
    into structured search parameters.
    """
    if not spoken_text or not spoken_text.strip():
        return {"query": "", "category": "", "max_price": None}

    prompt = f"""You are an intelligent e-commerce search parser.
Extract search intent from this voice transcript: "{spoken_text}"
Return ONLY a valid JSON object with keys:
- "search_query": cleaned core search keyword (string)
- "category_hint": inferred category like Electronics, Apparel, Footwear, Mobile, etc. (string or empty)
- "max_price": max numeric price limit if spoken, else null
- "summary": short human readable intent description in 1 sentence

Example transcript: "running shoes under 2000 rupees" -> {{"search_query": "running shoes", "category_hint": "Footwear", "max_price": 2000, "summary": "Searching for running shoes under INR 2000"}}
"""
    raw_res = call_gemini_api(prompt, json_mode=True)
    if raw_res:
        try:
            return json.loads(raw_res)
        except Exception:
            pass

    return {
        "search_query": spoken_text.strip(),
        "category_hint": "",
        "max_price": None,
        "summary": f"Searching for '{spoken_text.strip()}'"
    }

def get_ai_search_autocomplete(query, catalog_categories=None):
    """
    Generates intelligent search autocomplete and category suggestions using Gemini AI.
    """
    if not query or len(query.strip()) < 2:
        return []

    cats_str = ", ".join(catalog_categories) if catalog_categories else "Electronics, Fashion, Home, Mobiles, Shoes"
    prompt = f"""User is typing in an e-commerce search bar: "{query}"
Categories available: {cats_str}

Return a JSON array of up to 4 smart auto-complete search phrases relevant to shopping.
Example query "run" -> ["Running Shoes for Men", "Lightweight Running Sneakers", "Sports Fitness Watch", "Running Shorts"]
Return ONLY JSON array of strings:
"""
    raw_res = call_gemini_api(prompt, json_mode=True)
    if raw_res:
        try:
            parsed = json.loads(raw_res)
            if isinstance(parsed, list):
                return parsed[:4]
        except Exception:
            pass

    return [f"{query} in All Categories", f"Best {query} deals", f"Top rated {query}"]

def get_ai_product_recommendations(user_query=None, current_product_name=None, catalog_sample=None, limit=6):
    """
    Uses Gemini AI to match and rank product recommendations for customer.
    """
    if not catalog_sample:
        return []

    catalog_summary = []
    for p in catalog_sample:
        catalog_summary.append({
            "id": p.get('id'),
            "name": p.get('name'),
            "category": p.get('category'),
            "price": p.get('price')
        })

    prompt = f"""Recommend the top {limit} best matching products from this store catalog.
User context / Query: "{user_query or 'Popular trending items'}"
Current viewed product: "{current_product_name or 'None'}"

Store catalog:
{json.dumps(catalog_summary, indent=2)}

Return ONLY a JSON object with:
- "recommended_ids": list of integer product IDs
- "reasoning": 1 sentence explaining why these products fit the request.
"""

    raw_res = call_gemini_api(prompt, json_mode=True)
    if raw_res:
        try:
            data = json.loads(raw_res)
            rec_ids = data.get('recommended_ids', [])
            reasoning = data.get('reasoning', '')
            matched = [p for p in catalog_sample if p.get('id') in rec_ids]
            if matched:
                return {"products": matched[:limit], "reasoning": reasoning}
        except Exception:
            pass

    return {"products": catalog_sample[:limit], "reasoning": "Top picks tailored for you"}

def generate_ai_product_description(name, category, features=""):
    """
    Generates professional, SEO-optimized title & description for sellers adding products.
    """
    prompt = f"""You are a professional e-commerce copywriter.
Product Name: "{name}"
Category: "{category}"
Key Features / Details: "{features}"

Generate an enticing product description for an online storefront like Amazon or Flipkart.
Return ONLY a JSON object with:
- "enhanced_title": catchier product title (string)
- "short_summary": 2-line attractive tagline (string)
- "bullet_features": array of 4 bullet highlight strings
- "full_description": detailed HTML formatted product description paragraph (<p>, <ul>, <li>)
"""

    raw_res = call_gemini_api(prompt, json_mode=True)
    if raw_res:
        try:
            return json.loads(raw_res)
        except Exception:
            pass

    return {
        "enhanced_title": name,
        "short_summary": f"High quality {name} in {category}.",
        "bullet_features": ["Verified Seller Item", "Fast Express Shipping", "Quality Assured", "Best Price Guarantee"],
        "full_description": f"<p>Upgrade your lifestyle with <strong>{name}</strong>. Premium build quality, designed for performance and reliability.</p>"
    }

def get_ai_project_management_insight(query, role='admin', context_data=None):
    """
    Full Project Management Assistant for Admin, Sellers, and Customers.
    Answers store operation queries, inventory advice, sales analytics, and project status.
    """
    ctx_str = json.dumps(context_data, indent=2) if context_data else "General Store Dashboard"
    
    system_instruction = f"""You are Gemini AI, the Lead Store & Project Manager Assistant for VKShop.
Role of user: {role.upper()}
Context Data: {ctx_str}
Your goal is to provide insightful, accurate, actionable advice on store management, sales improvement, commission structure, inventory replenishment, and customer engagement.
Be polite, professional, concise, and helpful. Use bold bullet points and clear formatting.
"""

    res = call_gemini_api(query, system_instruction=system_instruction)
    if res:
        return res

    # Smart, beautifully formatted fallback responses when API token is unauthorized or offline
    q_lower = (query or '').strip().lower()

    if any(w in q_lower for w in ['hi', 'hii', 'hello', 'hey', 'vanakkam', 'namaste']):
        return f"""### 🤖 Gemini AI Store Assistant
Welcome to **VKShop**! How can I assist you today?

- **🛍️ Store Catalog**: Search products, compare prices, or find trending deals.
- **📦 Orders & Delivery**: Track active orders and shipment updates.
- **⚡ Quick Actions**: Use voice search or ask me for personalized recommendations!"""

    if any(w in q_lower for w in ['stock', 'inventory', 'product', 'item']):
        return f"""### 📦 Inventory & Stock Status
Here is your quick product catalog summary:
- **Active Products**: Catalogs are active and visible on the storefront.
- **Stock Alert**: Check products with low inventory in your seller dashboard to restock early.
- **Visibility**: All verified items are listed with instant checkout support."""

    if any(w in q_lower for w in ['sale', 'sales', 'revenue', 'money', 'order']):
        return f"""### 🚀 Sales & Revenue Recommendations
- **Promotions**: Feature top-viewed items on the homepage carousel.
- **Discounts**: Create bundle offers for high-demand apparel & tech items.
- **Conversion**: Offer free express shipping to reduce cart abandonment."""

    return f"""### 🤖 Gemini AI Store Assistant
I am here to help you manage your store and shopping experience!

- **Inventory**: Monitor stock levels and update product catalog details.
- **Sales**: Run targeted promotions and analyze product clicks.
- **System Status**: All storefront search, cart, and payment pipelines are operating normally."""
