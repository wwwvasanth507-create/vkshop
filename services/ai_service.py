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

def fetch_user_live_db_context(query_text, user):
    """
    Fetches real-time database records strictly scoped to user.id and user.role.
    Security: Passwords, password_hash, and secret keys are NEVER exposed.
    """
    if not user or not hasattr(user, 'id'):
        return {"role": "Guest"}

    try:
        from models import Order, OrderItem, CartItem, Wishlist, Product, StoreProfile, Address
        
        q_lower = (query_text or '').strip().lower()
        context = {
            "user_id": user.id,
            "username": getattr(user, 'username', 'Customer'),
            "email": getattr(user, 'email', ''),
            "role": getattr(user, 'role', 'customer')
        }

        # -------------------------------------------------------------
        # 1. CUSTOMER ROLE (Strictly scoped to user.id)
        # -------------------------------------------------------------
        if user.role in ['customer', 'user']:
            # Customer Orders
            if any(w in q_lower for w in ['order', 'purchase', 'bought', 'tracking', 'delivery', 'shipment', 'my orders']):
                orders = Order.query.filter_by(user_id=user.id).order_by(Order.created_at.desc()).limit(10).all()
                order_list = []
                for o in orders:
                    items_detail = []
                    for item in o.items:
                        items_detail.append(f"{item.product_name} (x{item.quantity}) - INR {item.total_price:.2f}")

                    order_list.append({
                        "order_number": o.order_number,
                        "status": o.status,
                        "grand_total": f"INR {o.grand_total:.2f}",
                        "date": o.created_at.strftime('%Y-%m-%d %H:%M') if o.created_at else "",
                        "tracking": o.tracking_number or "Processing",
                        "courier": o.courier_partner or "Standard",
                        "items_summary": ", ".join(items_detail) if items_detail else "Items"
                    })
                context['my_orders'] = order_list

            # Customer Cart
            if any(w in q_lower for w in ['cart', 'basket', 'my cart']):
                cart_items = CartItem.query.filter_by(user_id=user.id).all()
                context['my_cart'] = [{
                    "product_name": c.product.name if c.product else "Item",
                    "quantity": c.quantity,
                    "price": f"INR {c.product.offer_price:.2f}" if c.product else "0.00"
                } for c in cart_items]

            # Customer Wishlist
            if any(w in q_lower for w in ['wishlist', 'saved', 'my wishlist']):
                wish_items = Wishlist.query.filter_by(user_id=user.id).all()
                context['my_wishlist'] = [w.product.name for w in wish_items if w.product]

            # Customer Profile & Wallet
            if any(w in q_lower for w in ['account', 'profile', 'wallet', 'points', 'balance', 'my profile']):
                default_addr = Address.query.filter_by(user_id=user.id, is_default=True).first() or Address.query.filter_by(user_id=user.id).first()
                context['my_profile'] = {
                    "username": user.username,
                    "email": user.email,
                    "wallet_balance": f"INR {getattr(user, 'wallet_balance', 0.0):.2f}",
                    "reward_points": getattr(user, 'reward_points_balance', 0),
                    "shipping_address": f"{default_addr.addressLine1}, {default_addr.city}, {default_addr.state} ({default_addr.postalCode})" if default_addr else "No shipping address on file"
                }

        # -------------------------------------------------------------
        # 2. SELLER ROLE (Strictly scoped to seller's store)
        # -------------------------------------------------------------
        elif user.role == 'seller':
            store = getattr(user, 'store_profile', None)
            if store:
                context['store_profile'] = {
                    "store_name": store.name,
                    "rating": store.rating,
                    "total_sales": f"INR {store.total_sales:.2f}",
                    "commission_due": f"INR {store.commission_due:.2f}",
                    "commission_status": store.commission_payment_status
                }

                if any(w in q_lower for w in ['product', 'stock', 'inventory', 'my products']):
                    prods = Product.query.filter_by(seller_id=store.id).all()
                    context['my_store_products'] = [{
                        "name": p.name,
                        "price": f"INR {p.offer_price:.2f}",
                        "stock": p.stock,
                        "out_of_stock": p.is_out_of_stock
                    } for p in prods]

                if any(w in q_lower for w in ['order', 'sale', 'my orders', 'seller orders']):
                    seller_items = OrderItem.query.join(Product).filter(Product.seller_id == store.id).all()
                    context['my_store_orders'] = [{
                        "order_number": item.order.order_number if item.order else "N/A",
                        "product_name": item.product_name,
                        "qty": item.quantity,
                        "total": f"INR {item.total_price:.2f}",
                        "status": item.order.status if item.order else "N/A"
                    } for item in seller_items]

        # -------------------------------------------------------------
        # 3. ADMIN ROLE (Aggregate Metrics)
        # -------------------------------------------------------------
        elif user.role in ['admin', 'sub_admin']:
            from models import User, StoreProfile
            context['platform_metrics'] = {
                "total_users": User.query.count(),
                "total_sellers": StoreProfile.query.count(),
                "total_products": Product.query.count(),
                "total_orders": Order.query.count()
            }

        return context
    except Exception as err:
        logger.warning(f"Error fetching live DB context for AI: {err}")
        return {"role": getattr(user, 'role', 'customer')}

def get_ai_project_management_insight(query, role='admin', context_data=None, user=None):
    """
    Full Project Management & Customer Assistant.
    Reads live SQL database records scoped to user.id and responds accurately.
    """
    # If user object passed, pull live DB records
    if user:
        db_context = fetch_user_live_db_context(query, user)
        if context_data and isinstance(context_data, dict):
            context_data.update(db_context)
        else:
            context_data = db_context

    ctx_str = json.dumps(context_data, indent=2) if context_data else "General Store View"
    
    system_instruction = f"""You are Gemini AI, the Personal Assistant & Store Manager for VKShop.
User Role: {role.upper()}
Live Database Context: {ctx_str}

CRITICAL RULES:
1. Answer the user's request based on their live database records in `Live Database Context`.
2. NEVER mention passwords, hashes, or security keys.
3. If user asks "my orders", list their real orders with order number, items, total price, and status.
4. If user asks "my cart", list their cart items.
5. If user asks "my account" or "my profile", list their account summary.
6. Use clean Markdown formatting with headers (###), bold text (**bold**), and bullet points (- item).
"""

    res = call_gemini_api(query, system_instruction=system_instruction)
    if res:
        return res

    # Smart, formatted real database fallbacks when AI service is offline
    q_lower = (query or '').strip().lower()

    # My Orders Handler
    if any(w in q_lower for w in ['my order', 'my orders', 'order history', 'list my orders']):
        my_orders = context_data.get('my_orders', []) if context_data else []
        if my_orders:
            lines = ["### 📦 Your Orders\n"]
            for o in my_orders:
                lines.append(f"- **Order #{o['order_number']}** ({o['date']})")
                lines.append(f"  - **Status**: `{o['status']}`")
                lines.append(f"  - **Total**: **{o['grand_total']}**")
                lines.append(f"  - **Items**: {o['items_summary']}")
                lines.append(f"  - **Tracking**: {o['courier']} ({o['tracking']})\n")
            return "\n".join(lines)
        else:
            return "### 📦 Your Orders\nYou currently have no orders placed on VKShop."

    # My Cart Handler
    if any(w in q_lower for w in ['my cart', 'cart items', 'basket']):
        my_cart = context_data.get('my_cart', []) if context_data else []
        if my_cart:
            lines = ["### 🛒 Your Shopping Cart\n"]
            for c in my_cart:
                lines.append(f"- **{c['product_name']}** — Qty: {c['quantity']} ({c['price']})")
            return "\n".join(lines)
        else:
            return "### 🛒 Your Shopping Cart\nYour cart is currently empty."

    # My Profile / Account Handler
    if any(w in q_lower for w in ['my account', 'my profile', 'my balance', 'my address']):
        prof = context_data.get('my_profile', {}) if context_data else {}
        if prof:
            return f"""### 👤 Your Account Summary
- **Username**: **{prof.get('username', 'N/A')}**
- **Email**: {prof.get('email', 'N/A')}
- **Wallet Balance**: **{prof.get('wallet_balance', 'INR 0.00')}**
- **Reward Points**: **{prof.get('reward_points', 0)}**
- **Default Address**: {prof.get('shipping_address', 'None')}"""

    # Greetings Handler
    if any(w in q_lower for w in ['hi', 'hii', 'hello', 'hey', 'vanakkam', 'namaste']):
        username = getattr(user, 'username', 'Customer') if user else 'Customer'
        return f"""### 🤖 Gemini AI Personal Assistant
Welcome **{username}**! How can I assist you today?

- **📦 Orders**: Type `"my orders"` to view your orders & tracking status.
- **🛒 Cart**: Type `"my cart"` to view items saved in your cart.
- **👤 Account**: Type `"my profile"` to view your wallet balance & address.
- **🛍️ Catalog**: Ask me for product recommendations or deals!"""

    if any(w in q_lower for w in ['stock', 'inventory', 'product', 'item']):
        return f"""### 📦 Inventory & Catalog Overview
- **Active Products**: Catalogs are active and visible on storefront.
- **Stock Alert**: Check products with low inventory in seller dashboard.
- **Instant Checkout**: All listed items support instant secure ordering."""

    return f"""### 🤖 Gemini AI Store Assistant
I am here to help you with your account and shopping experience!

- **My Orders**: Type `"my orders"` to view your order history.
- **My Cart**: Type `"my cart"` to see cart items.
- **My Account**: Type `"my profile"` for wallet balance."""
