from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_login import login_required, current_user
from database import db
from models import Product, ProductVariant, ProductImage, Category, Brand, StoreProfile, OrderItem, Review, QuestionAnswer, AuditLog, Order
import uuid
import os
import json
from werkzeug.utils import secure_filename
from datetime import datetime

seller_bp = Blueprint('seller', __name__)

@seller_bp.before_request
@login_required
def check_seller_role():
    # Admins bypass seller checks
    if current_user.role == 'admin':
        return
        
    # Verifiers bypass checks for their endpoints
    if current_user.role == 'verifier' and request.endpoint and request.endpoint.startswith('seller.verifier_'):
        return
        
    if current_user.role != 'seller':
        flash("Unauthorized area. Sellers only.", "danger")
        return redirect(url_for('main.index'))
        
    # Block unapproved sellers
    store = current_user.store_profile
    if not store:
        if request.endpoint != 'seller.store_settings':
            return redirect(url_for('seller.store_settings'))
        return
        
    if store.status != 'Approved':
        if request.endpoint not in ['seller.pending_approval', 'seller.store_settings']:
            return redirect(url_for('seller.pending_approval'))

@seller_bp.route('/pending-approval')
@login_required
def pending_approval():
    store = current_user.store_profile
    if store and store.status == 'Approved':
        return redirect(url_for('seller.dashboard'))
    return render_template('errors/pending_approval.html', store=store)

def log_audit(action, details=None):
    from routes.auth import log_audit as core_log
    core_log(current_user, action, details)

def notify_user(user_id, title, message, type='general'):
    """Disabled globally per user request."""
    pass

@seller_bp.route('/dashboard')
def dashboard():
    store = current_user.store_profile
    if not store:
        flash("Please create a store profile first.", "warning")
        return redirect(url_for('seller.store_settings'))
        
    products = Product.query.filter_by(seller_id=store.id).all()
    
    # Calculate store stats
    from models import Order, Payment
    
    # Lifetime sales (Total of confirmed/paid orders)
    confirmed_order_items = OrderItem.query.join(Product).join(Order).filter(
        Product.seller_id == store.id,
        Order.status.in_(['Confirmed', 'Packed', 'Shipped', 'Out For Delivery', 'Delivered'])
    ).all()
    sales_total = sum(item.total_price for item in confirmed_order_items)

    # Order count
    completed_orders = Order.query.join(OrderItem).join(Product).join(Payment).filter(
        Product.seller_id == store.id,
        Order.status == 'Delivered',
        Payment.status == 'Completed'
    ).distinct().all()
    orders_count = len(completed_orders)
    
    # Highest clicked product
    highest_click_product = None
    if products:
        highest_click_product = max(products, key=lambda p: p.clicks)
    
    # Traffic metrics
    total_views = sum(p.views for p in products)
    total_clicks = sum(p.clicks for p in products)
    
    # Chart dataset (top 5 products by views)
    top_products = sorted(products, key=lambda x: x.views, reverse=True)[:5]
    chart_labels = [p.name[:12] + '...' if len(p.name) > 12 else p.name for p in top_products]
    chart_views = [p.views for p in top_products]
    chart_clicks = [p.clicks for p in top_products]
    
    # Weekly sales data (real) — last 7 days
    from datetime import timedelta
    today = datetime.utcnow()
    week_offset = request.args.get('week_offset', 0, type=int)
    start_of_week = today - timedelta(days=today.weekday()) - timedelta(weeks=week_offset)  # Monday
    week_sales_labels = []
    week_sales_data = []
    week_day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    for i in range(7):
        day_start = start_of_week + timedelta(days=i)
        day_end = day_start + timedelta(days=1)
        day_sales = db.session.query(db.func.coalesce(db.func.sum(OrderItem.total_price), 0)).join(
            Order, OrderItem.order_id == Order.id
        ).join(
            Product, OrderItem.product_id == Product.id
        ).filter(
            Product.seller_id == store.id,
            Order.created_at >= day_start,
            Order.created_at < day_end,
            Order.status.in_(['Confirmed', 'Packed', 'Shipped', 'Out For Delivery', 'Delivered'])
        ).scalar()
        week_sales_labels.append(week_day_names[i])
        week_sales_data.append(float(day_sales))
    
    total_weekly_sales = sum(week_sales_data)
    
    # Low stock check (threshold: 3)
    low_stock = []
    for prod in products:
        if prod.variants:
            for var in prod.variants:
                if var.stock <= 3:
                    low_stock.append((prod, var))
        else:
            if prod.stock <= 3:
                low_stock.append((prod, None))
                
    # Reviews
    product_ids = [p.id for p in products]
    reviews = Review.query.filter(Review.product_id.in_(product_ids)).order_by(Review.created_at.desc()).all() if product_ids else []
    
    # Load notices
    from models import SellerNotice
    notices = SellerNotice.query.filter((SellerNotice.store_id == None) | (SellerNotice.store_id == store.id)).order_by(SellerNotice.created_at.desc()).all()

    # Orders for this seller
    from models import ReturnRequest, SupportTicket, CommissionPayment, CommissionReport
    from routes.admin import get_setting
    enable_out_for_delivery = get_setting('ENABLE_OUT_FOR_DELIVERY', True)
    enable_delivered = get_setting('ENABLE_DELIVERED', True)
    
    filter_date = request.args.get('order_date', '').strip()
    filter_status = request.args.get('order_status', 'All').strip()
    
    q = Order.query.join(OrderItem).filter(
        OrderItem.product.has(seller_id=store.id)
    )
    
    if filter_date:
        try:
            dt = datetime.strptime(filter_date, '%Y-%m-%d').date()
            q = q.filter(db.func.date(Order.created_at) == dt)
        except ValueError:
            pass
            
    if filter_status and filter_status != 'All':
        db_status = filter_status
        if filter_status == 'Ordered':
            db_status = 'Pending'
        if db_status == 'Out For Delivery' and not enable_out_for_delivery:
            db_status = 'INVALID'
        elif db_status == 'Delivered' and not enable_delivered:
            db_status = 'INVALID'
        q = q.filter(Order.status == db_status)
        
    seller_orders = q.order_by(Order.created_at.desc()).distinct().all()
    for o in seller_orders:
        status = o.status
        if status == 'Pending':
            status = 'Ordered'
        elif status == 'Packed':
            status = 'Confirmed'
            
        if status == 'Out For Delivery' and not enable_out_for_delivery:
            status = 'Shipped'
        elif status == 'Delivered':
            if not enable_delivered:
                if enable_out_for_delivery:
                    status = 'Out For Delivery'
                else:
                    status = 'Shipped'
        o.visible_status = status

    # Return requests for this seller's products
    seller_returns = ReturnRequest.query.join(
        OrderItem, ReturnRequest.order_item_id == OrderItem.id
    ).filter(
        OrderItem.product_id.in_(product_ids)
    ).order_by(ReturnRequest.created_at.desc()).all() if product_ids else []

    # Support tickets from customers who ordered from this seller
    buyer_ids = list({o.user_id for o in seller_orders})
    seller_tickets = SupportTicket.query.filter(
        SupportTicket.user_id.in_(buyer_ids)
    ).order_by(SupportTicket.created_at.desc()).all() if buyer_ids else []

    # Commission history - show ALL statuses including Rejected
    commission_history = CommissionPayment.query.filter_by(store_id=store.id).order_by(CommissionPayment.created_at.desc()).all()
    commission_due = store.commission_due
    
    # Commission reports
    commission_reports = CommissionReport.query.filter_by(store_id=store.id).order_by(CommissionReport.created_at.desc()).all()
    
    # Commission payment status check - Don't auto-hide submitted payments
    show_commission_alert = store.commission_payment_status in ['Requested', 'Suspended', 'Submitted']
    
    return render_template(
        'seller/dashboard.html',
        store=store,
        products=products,
        sales_total=sales_total,
        orders_count=orders_count,
        total_views=total_views,
        total_clicks=total_clicks,
        chart_labels=chart_labels,
        chart_views=chart_views,
        chart_clicks=chart_clicks,
        low_stock=low_stock,
        reviews=reviews,
        notices=notices,
        highest_click_product=highest_click_product,
        seller_orders=seller_orders,
        seller_returns=seller_returns,
        seller_tickets=seller_tickets,
        commission_history=commission_history,
        commission_due=commission_due,
        enable_out_for_delivery=enable_out_for_delivery,
        enable_delivered=enable_delivered,
        week_sales_labels=week_sales_labels,
        week_sales_data=week_sales_data,
        total_weekly_sales=total_weekly_sales,
        week_offset=week_offset,
        show_commission_alert=show_commission_alert,
        commission_reports=commission_reports
    )

# ----------------- STORE PROFILE SETTINGS -----------------
@seller_bp.route('/store/settings', methods=['GET', 'POST'])
def store_settings():
    store = current_user.store_profile
    if not store:
        # Create default
        store = StoreProfile(user_id=current_user.id, name=f"{current_user.username}'s Store")
        db.session.add(store)
        db.session.commit()
        
    if request.method == 'POST':
        store.name = request.form.get('name', '').strip()
        store.description = request.form.get('description', '').strip()
        store.tax_number = request.form.get('tax_number', '').strip()
        store.upi_id = request.form.get('upi_id', '').strip()
        store.store_address = request.form.get('store_address', '').strip()
        store.store_contact = request.form.get('store_contact', '').strip()
        
        # Files upload (logo / banner / qr_code)
        from services.storage import upload_file_field, storage_service
        
        logo_file = request.files.get('logo')
        if logo_file and logo_file.filename:
            old_logo = store.logo
            key, err = upload_file_field(logo_file, 'stores')
            if err:
                flash(f"Failed to upload logo: {err}", "danger")
            elif key:
                store.logo = key
                if old_logo and old_logo != key:
                    storage_service.delete_file(old_logo)
            
        banner_file = request.files.get('banner')
        if banner_file and banner_file.filename:
            old_banner = store.banner
            key, err = upload_file_field(banner_file, 'stores/banners')
            if err:
                flash(f"Failed to upload banner: {err}", "danger")
            elif key:
                store.banner = key
                if old_banner and old_banner != key:
                    storage_service.delete_file(old_banner)
            
        qr_file = request.files.get('qr_code')
        if qr_file and qr_file.filename:
            old_qr = store.qr_code_path
            key, err = upload_file_field(qr_file, 'stores/qr')
            if err:
                flash(f"Failed to upload QR code: {err}", "danger")
            elif key:
                store.qr_code_path = key
                if old_qr and old_qr != key:
                    storage_service.delete_file(old_qr)
            
        db.session.commit()
        log_audit("UPDATE_STORE_SETTINGS", f"Updated store details for: {store.name}")
        flash("Store profile updated.", "success")
        return redirect(request.referrer or url_for('seller.dashboard'))
        
    return render_template('seller/store_settings.html', store=store)

# ----------------- PRODUCT & VARIANT CRUD -----------------
def _parse_region_list(form_value):
    """Parse a newline/comma separated string into a cleaned list of strings."""
    raw = form_value or ''
    items = [item.strip() for part in raw.splitlines() for item in part.split(',')]
    return [item for item in items if item]

@seller_bp.route('/product/add', methods=['GET', 'POST'])
def add_product():
    store = current_user.store_profile
    categories = Category.query.all()
    brands = Brand.query.all()
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        category_id = request.form.get('category_id', type=int)
        brand_id_raw = request.form.get('brand_id', '').strip()
        brand_id = int(brand_id_raw) if brand_id_raw else None
        base_price = request.form.get('base_price', type=float)
        discount_percent = request.form.get('discount_percent', 0.0, type=float)
        delivery_days = request.form.get('delivery_days', 3, type=int)
        is_digital = True if request.form.get('is_digital') else False
        stock = request.form.get('stock', 0, type=int)
        
        countries = _parse_region_list(request.form.get('available_countries', ''))
        states = _parse_region_list(request.form.get('available_states', ''))
        districts = _parse_region_list(request.form.get('available_districts', ''))

        offer_price = round(base_price * (1.0 - (discount_percent / 100.0)), 2)
        sku = f"PROD-{uuid.uuid4().hex[:8].upper()}"
        slug = f"{secure_filename(name).lower()}-{uuid.uuid4().hex[:4]}"
        
        prod = Product(
            seller_id=store.id, category_id=category_id, brand_id=brand_id,
            name=name, slug=slug, description=description, base_price=base_price,
            discount_percent=discount_percent, offer_price=offer_price,
            tax_percentage=0.0, shipping_charges=0.0,
            delivery_days=delivery_days, stock=stock,
            sku=sku, is_digital=is_digital, is_active=True
        )
        prod.available_countries = countries
        prod.available_states = states
        prod.available_districts = districts
        db.session.add(prod)
        db.session.commit()
        
        image_file = request.files.get('primary_image')
        if image_file and image_file.filename:
            from services.storage import upload_file_field, storage_service
            key, err = upload_file_field(image_file, 'products')
            if err:
                db.session.rollback()
                flash(f"Failed to upload product image: {err}", "danger")
                return render_template('seller/add_product.html', categories=categories, brands=brands)
            if key:
                pimg = ProductImage(product_id=prod.id, image_path=key, is_primary=True)
                db.session.add(pimg)
                db.session.commit()
            
        log_audit("ADD_PRODUCT", f"Added product: {name} SKU: {sku}")
        flash("Product added successfully. Now add variants.", "success")
        return redirect(url_for('seller.edit_product', prod_id=prod.id))
        
    return render_template('seller/add_product.html', categories=categories, brands=brands)

@seller_bp.route('/product/edit/<int:prod_id>', methods=['GET', 'POST'])
def edit_product(prod_id):
    store = current_user.store_profile
    prod = Product.query.filter_by(id=prod_id, seller_id=store.id).first_or_404()
    categories = Category.query.all()
    brands = Brand.query.all()
    
    if request.method == 'POST':
        prod.name = request.form.get('name').strip()
        prod.description = request.form.get('description').strip()
        prod.category_id = request.form.get('category_id', type=int)
        brand_id_raw = request.form.get('brand_id', '').strip()
        prod.brand_id = int(brand_id_raw) if brand_id_raw else None
        prod.base_price = request.form.get('base_price', type=float)
        prod.discount_percent = request.form.get('discount_percent', 0.0, type=float)
        prod.delivery_days = request.form.get('delivery_days', 3, type=int)
        prod.is_digital = True if request.form.get('is_digital') else False
        prod.stock = request.form.get('stock', 0, type=int)

        prod.offer_price = round(prod.base_price * (1.0 - (prod.discount_percent / 100.0)), 2)
        prod.tax_percentage = 0.0
        prod.shipping_charges = 0.0

        prod.available_countries = _parse_region_list(request.form.get('available_countries', ''))
        prod.available_states = _parse_region_list(request.form.get('available_states', ''))
        prod.available_districts = _parse_region_list(request.form.get('available_districts', ''))
        
        specs = {}
        spec_keys = request.form.getlist('spec_key')
        spec_vals = request.form.getlist('spec_val')
        for k, v in zip(spec_keys, spec_vals):
            if k.strip():
                specs[k.strip()] = v.strip()
        prod.specifications = specs
        
        from services.storage import upload_file_field, storage_service
        gallery_files = request.files.getlist('gallery_images')
        uploaded_keys = []
        for g_file in gallery_files:
            if g_file and g_file.filename:
                key, err = upload_file_field(g_file, 'products')
                if err:
                    for k in uploaded_keys:
                        storage_service.delete_file(k)
                    db.session.rollback()
                    flash(f"Gallery image upload failed: {err}", "danger")
                    return redirect(request.referrer or url_for('seller.edit_product', prod_id=prod.id))
                if key:
                    uploaded_keys.append(key)
                    pimg = ProductImage(product_id=prod.id, image_path=key, is_primary=False)
                    db.session.add(pimg)
                
        db.session.commit()
        log_audit("EDIT_PRODUCT", f"Updated product ID: {prod_id}")
        flash("Product updated successfully.", "success")
        return redirect(request.referrer or url_for('seller.dashboard'))
        
    return render_template('seller/edit_product.html', product=prod, categories=categories, brands=brands)

@seller_bp.route('/product/delete/<int:prod_id>')
def delete_product(prod_id):
    store = current_user.store_profile
    prod = Product.query.filter_by(id=prod_id, seller_id=store.id).first_or_404()
    
    from services.storage import storage_service
    for img in prod.images:
        if img.image_path:
            storage_service.delete_file(img.image_path)
    for var in prod.variants:
        if var.image_path:
            storage_service.delete_file(var.image_path)
            
    db.session.delete(prod)
    db.session.commit()
    log_audit("DELETE_PRODUCT", f"Deleted product ID: {prod_id}")
    flash("Product deleted successfully.", "success")
    return redirect(url_for('seller.dashboard') + '#products')

@seller_bp.route('/product/image/delete/<int:img_id>')
def delete_product_image(img_id):
    store = current_user.store_profile
    img = ProductImage.query.join(Product).filter(
        ProductImage.id == img_id,
        Product.seller_id == store.id
    ).first_or_404()
    prod_id = img.product_id
    
    from services.storage import storage_service
    if img.image_path:
        storage_service.delete_file(img.image_path)
        
    db.session.delete(img)
    db.session.commit()
    log_audit("DELETE_PRODUCT_IMAGE", f"Deleted image ID {img_id}")
    flash("Product image deleted.", "success")
    return redirect(request.referrer or url_for('seller.edit_product', prod_id=prod_id))

# ----------------- STOCK UPDATE ROUTES -----------------
@seller_bp.route('/product/<int:prod_id>/stock/update', methods=['POST'])
def update_product_stock(prod_id):
    store = current_user.store_profile
    prod = Product.query.filter_by(id=prod_id, seller_id=store.id).first_or_404()
    new_stock = request.form.get('stock', type=int)
    if new_stock is None or new_stock < 0:
        flash("Invalid stock quantity.", "danger")
        return redirect(request.referrer or url_for('seller.edit_product', prod_id=prod_id))
    prod.stock = new_stock
    db.session.commit()
    log_audit("UPDATE_BASE_STOCK", f"Product ID {prod_id} base stock set to {new_stock}")
    flash(f"Base product stock updated to {new_stock}.", "success")
    return redirect(request.referrer or url_for('seller.edit_product', prod_id=prod_id))

@seller_bp.route('/variant/<int:var_id>/stock/update', methods=['POST'])
def update_variant_stock(var_id):
    store = current_user.store_profile
    var = ProductVariant.query.filter_by(id=var_id).first_or_404()
    prod = Product.query.filter_by(id=var.product_id, seller_id=store.id).first_or_404()
    new_stock = request.form.get('stock', type=int)
    if new_stock is None or new_stock < 0:
        flash("Invalid stock quantity.", "danger")
        return redirect(request.referrer or url_for('seller.edit_product', prod_id=prod.id))
    var.stock = new_stock
    db.session.commit()
    log_audit("UPDATE_VARIANT_STOCK", f"Variant ID {var_id} stock set to {new_stock}")
    flash(f"Variant stock updated to {new_stock}.", "success")
    return redirect(request.referrer or url_for('seller.edit_product', prod_id=prod.id))

# ----------------- PRODUCT VARIANTS CRUD -----------------
@seller_bp.route('/product/<int:prod_id>/variant/add', methods=['POST'])
def add_variant(prod_id):
    store = current_user.store_profile
    prod = Product.query.filter_by(id=prod_id, seller_id=store.id).first_or_404()
    
    sku = request.form.get('sku', '').strip() or f"VAR-{uuid.uuid4().hex[:8].upper()}"
    stock = request.form.get('stock', 0, type=int)
    price = request.form.get('price', type=float)
    color = request.form.get('color', '').strip()
    size = request.form.get('size', '').strip()
    ram = request.form.get('ram', '').strip()
    storage = request.form.get('storage', '').strip()
    weight = request.form.get('weight', 0.0, type=float)
    
    image_fn = None
    var_image = request.files.get('variant_image')
    if var_image and var_image.filename:
        from services.storage import upload_file_field
        key, err = upload_file_field(var_image, 'products/variants')
        if err:
            flash(f"Failed to upload variant image: {err}", "danger")
            return redirect(request.referrer or url_for('seller.edit_product', prod_id=prod.id))
        image_fn = key
        
    var = ProductVariant(
        product_id=prod.id, sku=sku, stock=stock, price=price,
        color=color, size=size, ram=ram, storage=storage,
        weight=weight, image_path=image_fn
    )
    db.session.add(var)
    db.session.commit()
    
    log_audit("ADD_PRODUCT_VARIANT", f"Added variant to product ID {prod_id}: SKU {sku}")
    flash("Variant added.", "success")
    return redirect(request.referrer or url_for('seller.edit_product', prod_id=prod.id))

@seller_bp.route('/variant/delete/<int:var_id>')
def delete_variant(var_id):
    store = current_user.store_profile
    var = ProductVariant.query.filter_by(id=var_id).first_or_404()
    prod = Product.query.filter_by(id=var.product_id, seller_id=store.id).first_or_404()
    
    if var.image_path:
        from services.storage import storage_service
        storage_service.delete_file(var.image_path)
        
    db.session.delete(var)
    db.session.commit()
    log_audit("DELETE_PRODUCT_VARIANT", f"Deleted variant ID {var_id}")
    flash("Variant deleted.", "success")
    return redirect(request.referrer or url_for('seller.edit_product', prod_id=prod.id))

# ----------------- MARK ORDER SHIPPED -----------------
@seller_bp.route('/order/<int:order_id>/ship', methods=['POST'])
def mark_order_shipped(order_id):
    from flask import jsonify
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.args.get('ajax') == 'true'

    store = current_user.store_profile
    order = Order.query.join(OrderItem).filter(
        Order.id == order_id,
        OrderItem.product.has(seller_id=store.id)
    ).first_or_404()

    if order.status not in ['Confirmed', 'Packed']:
        if is_ajax:
            return jsonify(success=False, error="Only Confirmed orders can be marked as Shipped.")
        return redirect(url_for('seller.dashboard') + '#orders')

    courier_name = request.form.get('courier_name', '').strip()
    tracking_number = request.form.get('tracking_number', '').strip()

    if not courier_name or not tracking_number:
        if is_ajax:
            return jsonify(success=False, error="Both courier name and tracking number are required.")
        return redirect(url_for('seller.dashboard') + '#orders')

    order.status = 'Shipped'
    order.courier_partner = courier_name
    order.tracking_number = tracking_number
    order.updated_at = datetime.utcnow()
    db.session.commit()

    notify_user(order.user_id, 'Your Order Has Been Shipped!',
                f'Order {order.order_number} has been shipped via {courier_name}. Tracking Number: {tracking_number}', 'order')

    log_audit("MARK_ORDER_SHIPPED", f"Order {order.order_number} marked as Shipped. Courier: {courier_name}, Tracking: {tracking_number}")
    if is_ajax:
        return jsonify(success=True, order_id=order.id, status='Shipped')
    return redirect(url_for('seller.dashboard') + '#orders')

# ----------------- MARK ORDER OUT FOR DELIVERY -----------------
@seller_bp.route('/order/<int:order_id>/out_for_delivery', methods=['POST'])
def mark_order_out_for_delivery(order_id):
    from flask import jsonify
    from routes.admin import get_setting
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.args.get('ajax') == 'true'

    enable_out_for_delivery = get_setting('ENABLE_OUT_FOR_DELIVERY', True)
    if not enable_out_for_delivery:
        if is_ajax:
            return jsonify(success=False, error="Out for Delivery status is disabled by admin.")
        return redirect(url_for('seller.dashboard') + '#orders')

    store = current_user.store_profile
    order = Order.query.join(OrderItem).filter(
        Order.id == order_id,
        OrderItem.product.has(seller_id=store.id)
    ).first_or_404()

    if order.status != 'Shipped':
        if is_ajax:
            return jsonify(success=False, error="Only Shipped orders can be marked as Out for Delivery.")
        return redirect(url_for('seller.dashboard') + '#orders')

    order.status = 'Out For Delivery'
    order.updated_at = datetime.utcnow()
    db.session.commit()

    notify_user(order.user_id, 'Your Order is Out for Delivery!',
                f'Order {order.order_number} is out for delivery and will reach you soon.', 'order')

    log_audit("MARK_OUT_FOR_DELIVERY", f"Order {order.order_number} marked as Out For Delivery.")
    if is_ajax:
        return jsonify(success=True, order_id=order.id, status='Out For Delivery')
    return redirect(url_for('seller.dashboard') + '#orders')

# ----------------- MARK ORDER DELIVERED -----------------
@seller_bp.route('/order/<int:order_id>/deliver', methods=['POST'])
def mark_order_delivered(order_id):
    from flask import jsonify
    from routes.admin import get_setting
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.args.get('ajax') == 'true'

    enable_delivered = get_setting('ENABLE_DELIVERED', True)
    if not enable_delivered:
        if is_ajax:
            return jsonify(success=False, error="Delivered status is disabled by admin.")
        return redirect(url_for('seller.dashboard') + '#orders')

    store = current_user.store_profile
    order = Order.query.join(OrderItem).filter(
        Order.id == order_id,
        OrderItem.product.has(seller_id=store.id)
    ).first_or_404()

    enable_out_for_delivery = get_setting('ENABLE_OUT_FOR_DELIVERY', True)
    allowed_from = ['Out For Delivery'] if enable_out_for_delivery else ['Shipped']
    if order.status not in allowed_from:
        if is_ajax:
            return jsonify(success=False, error=f"Order must be in {' or '.join(allowed_from)} status to mark as Delivered.")
        return redirect(url_for('seller.dashboard') + '#orders')

    order.status = 'Delivered'
    order.updated_at = datetime.utcnow()

    if order.payment and order.payment.payment_method == 'COD' and order.payment.status == 'Pending':
        order.payment.status = 'Completed'

    db.session.commit()

    notify_user(order.user_id, 'Your Order Has Been Delivered!',
                f'Order {order.order_number} has been successfully delivered. Thank you for shopping with us!', 'order')

    log_audit("MARK_ORDER_DELIVERED", f"Order {order.order_number} marked as Delivered.")
    if is_ajax:
        return jsonify(success=True, order_id=order.id, status='Delivered')
    return redirect(url_for('seller.dashboard') + '#orders')

# ----------------- CUSTOMER QUESTIONS REPLIES -----------------
@seller_bp.route('/question/answer/<int:q_id>', methods=['POST'])
def answer_question(q_id):
    store = current_user.store_profile
    q = QuestionAnswer.query.get_or_404(q_id)
    prod = Product.query.get(q.product_id)
    if prod.seller_id != store.id:
        flash("Unauthorized answer.", "danger")
        return redirect(url_for('seller.dashboard') + '#qa')
        
    answer_text = request.form.get('answer', '').strip()
    if answer_text:
        q.answer = answer_text
        q.answered_by = current_user.id
        q.answered_at = datetime.utcnow()
        db.session.commit()
        log_audit("ANSWER_QUESTION", f"Answered question ID: {q_id}")
        flash("Question answered successfully.", "success")
    return redirect(url_for('seller.dashboard') + '#qa')

@seller_bp.route('/verifier/dashboard')
@login_required
def verifier_dashboard():
    if current_user.role != 'verifier':
        flash("Unauthorized access. Verifiers only.", "danger")
        return redirect(url_for('main.index'))
        
    if current_user.is_suspended:
        flash("Your account has been suspended.", "danger")
        return redirect(url_for('auth.logout'))
        
    store = StoreProfile.query.get_or_404(current_user.seller_id)
    
    from models import Order, Payment
    orders = Order.query.join(OrderItem).filter(
        OrderItem.product.has(seller_id=store.id)
    ).all()
    
    verifier_orders = []
    for o in set(orders):
        if not o.payment:
            continue
        if o.payment.payment_method == 'UPI' and o.payment.status == 'Awaiting Verification':
            verifier_orders.append(o)
        elif o.payment.payment_method != 'UPI' and o.status == 'Pending':
            verifier_orders.append(o)

    verifier_orders.sort(key=lambda o: o.created_at, reverse=True)

    return render_template('seller/verifier_dashboard.html', store=store, orders=verifier_orders)

@seller_bp.route('/verifier/verify/<int:order_id>')
@seller_bp.route('/verifier/confirm/<int:order_id>')
@login_required
def verifier_confirm_payment(order_id):
    from flask import jsonify
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.args.get('ajax') == 'true'

    if current_user.role != 'verifier':
        if is_ajax:
            return jsonify(success=False, error="Unauthorized access.")
        flash("Unauthorized access.", "danger")
        return redirect(request.referrer or url_for('main.index'))
        
    if current_user.is_suspended:
        if is_ajax:
            return jsonify(success=False, error="Your account has been suspended.")
        flash("Your account has been suspended.", "danger")
        return redirect(url_for('auth.logout'))
        
    from models import Order, RewardPoint
    order = Order.query.get_or_404(order_id)
    payment = order.payment

    is_upi_awaiting = bool(payment and payment.payment_method == 'UPI' and payment.status == 'Awaiting Verification')
    is_other_pending = bool(payment and payment.payment_method != 'UPI' and order.status == 'Pending')

    if is_upi_awaiting or is_other_pending:
        order.status = 'Confirmed'
        order.updated_at = datetime.utcnow()

        if is_upi_awaiting:
            payment.status = 'Completed'

            store = StoreProfile.query.get(current_user.seller_id)
            for item in order.items:
                store.balance += item.total_price
                store.total_sales += item.total_price

            earned_pts = int(order.total_amount / 100)
            if earned_pts > 0:
                db.session.add(RewardPoint(
                    user_id=order.user_id,
                    points=earned_pts,
                    type='credit',
                    description="Purchase reward points"
                ))

        db.session.commit()
        if is_ajax:
            return jsonify(success=True, order_id=order.id, status='Confirmed')
        flash(f"Order {order.order_number} verified and confirmed successfully!", "success")
    else:
        if is_ajax:
            return jsonify(success=False, error="This order is not awaiting verification.")
        flash("This order is not awaiting verification.", "warning")

    return redirect(request.referrer or url_for('seller.verifier_dashboard'))

@seller_bp.route('/verifier/cancel/<int:order_id>')
@login_required
def verifier_cancel_payment(order_id):
    from flask import jsonify
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.args.get('ajax') == 'true'

    if current_user.role != 'verifier':
        if is_ajax:
            return jsonify(success=False, error="Unauthorized access.")
        flash("Unauthorized access.", "danger")
        return redirect(request.referrer or url_for('main.index'))
        
    if current_user.is_suspended:
        if is_ajax:
            return jsonify(success=False, error="Your account has been suspended.")
        flash("Your account has been suspended.", "danger")
        return redirect(url_for('auth.logout'))
        
    from models import Order, Notification, RewardPoint
    order = Order.query.get_or_404(order_id)
    payment = order.payment

    is_upi_awaiting = bool(payment and payment.payment_method == 'UPI' and payment.status == 'Awaiting Verification')
    is_other_pending = bool(payment and payment.payment_method != 'UPI' and order.status == 'Pending')

    if is_upi_awaiting or is_other_pending:
        payment.status = 'Failed'
        payment.description = (
            'Your payment details is incorrect. So, the order is cancelled by the payment verifiers. '
            'If any trouble please make complaint with appropriate proofs. Thank You!'
        )
        order.status = 'Cancelled'
        order.updated_at = datetime.utcnow()

        for item in order.items:
            if item.variant_id and item.variant:
                item.variant.stock += item.quantity
            elif item.product_id and item.product:
                item.product.stock += item.quantity

        if is_other_pending:
            store = StoreProfile.query.get(current_user.seller_id)
            for item in order.items:
                store.balance -= item.total_price
                store.total_sales -= item.total_price

            earned_pts = int(order.total_amount / 100)
            if earned_pts > 0:
                db.session.add(RewardPoint(
                    user_id=order.user_id,
                    points=earned_pts,
                    type='debit',
                    description="Reversal - order cancelled by payment verifier"
                ))

        notif = Notification(
            user_id=order.user_id,
            title='Order Cancelled – Payment Verification Failed',
            message=(
                f'Your payment details for Order {order.order_number} is incorrect. '
                f'So, the order is cancelled by the payment verifiers. '
                f'If any trouble please make complaint with appropriate proofs. Thank You!'
            ),
            type='order'
        )
        db.session.add(notif)
        db.session.commit()

        log_audit(
            "VERIFIER_CANCEL_ORDER",
            f"Verifier {current_user.username} cancelled Order {order.order_number} due to payment verification failure."
        )
        if is_ajax:
            return jsonify(success=True, order_id=order.id, status='Cancelled')
        flash(f"Order {order.order_number} has been cancelled due to incorrect payment details.", "success")
    else:
        if is_ajax:
            return jsonify(success=False, error="This order cannot be cancelled — it is not awaiting verification.")
        flash("This order cannot be cancelled — it is not awaiting verification.", "warning")

    return redirect(request.referrer or url_for('seller.verifier_dashboard'))


@seller_bp.route('/verifiers', methods=['GET', 'POST'])
def verifiers():
    store = current_user.store_profile
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        
        if not username or not email or not password:
            flash("All fields are required.", "danger")
            return redirect(request.referrer or url_for('seller.verifiers'))
            
        from models import User
        if User.query.filter((User.username == username) | (User.email == email)).first():
            flash("Username or Email already in use.", "danger")
            return redirect(request.referrer or url_for('seller.verifiers'))
            
        verifier_user = User(
            username=username,
            email=email,
            role='verifier',
            seller_id=store.id,
            is_active=True
        )
        verifier_user.set_password(password)
        db.session.add(verifier_user)
        db.session.commit()
        
        log_audit("CREATE_VERIFIER", f"Created verifier account: {username}")
        flash(f"Verifier '{username}' created successfully.", "success")
        return redirect(request.referrer or url_for('seller.verifiers'))
        
    from models import User
    verifier_list = User.query.filter_by(role='verifier', seller_id=store.id).all()
    return render_template('seller/verifiers.html', verifiers=verifier_list)

@seller_bp.route('/verifier/edit/<int:v_id>', methods=['POST'])
def edit_verifier(v_id):
    store = current_user.store_profile
    from models import User
    verifier = User.query.filter_by(id=v_id, seller_id=store.id).first_or_404()
    
    username = request.form.get('username', '').strip()
    email = request.form.get('email', '').strip()
    password = request.form.get('password', '')
    
    if username:
        verifier.username = username
    if email:
        verifier.email = email
    if password:
        verifier.set_password(password)
        
    db.session.commit()
    flash(f"Verifier details updated.", "success")
    return redirect(request.referrer or url_for('seller.verifiers'))

@seller_bp.route('/verifier/toggle-suspend/<int:v_id>')
def toggle_suspend_verifier(v_id):
    store = current_user.store_profile
    from models import User
    verifier = User.query.filter_by(id=v_id, seller_id=store.id).first_or_404()
    verifier.is_suspended = not verifier.is_suspended
    db.session.commit()
    
    status = "suspended" if verifier.is_suspended else "activated"
    flash(f"Verifier '{verifier.username}' has been {status}.", "success")
    return redirect(request.referrer or url_for('seller.verifiers'))

@seller_bp.route('/verifier/delete/<int:v_id>')
def delete_verifier(v_id):
    store = current_user.store_profile
    from models import User
    verifier = User.query.filter_by(id=v_id, seller_id=store.id).first_or_404()
    db.session.delete(verifier)
    db.session.commit()
    
    flash("Verifier account deleted successfully.", "success")
    return redirect(request.referrer or url_for('seller.verifiers'))

@seller_bp.route('/orders/download-cid')
def download_cid():
    store = current_user.store_profile
    
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    
    query = Order.query.join(OrderItem).filter(
        OrderItem.product.has(seller_id=store.id),
        Order.status == 'Confirmed'
    )
    
    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            query = query.filter(Order.updated_at >= start_date)
        except ValueError:
            pass
            
    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
            query = query.filter(Order.updated_at <= end_date)
        except ValueError:
            pass
            
    orders = query.order_by(Order.updated_at.desc()).all()
    seller_orders = list(set(orders))
    
    return render_template(
        'seller/download_cid.html',
        orders=seller_orders,
        now=datetime.utcnow()
    )

@seller_bp.route('/feedback', methods=['POST'])
def submit_feedback():
    store = current_user.store_profile
    message = request.form.get('message', '').strip()
    if not message:
        flash("Feedback cannot be empty.", "danger")
        return redirect(url_for('seller.dashboard') + '#feedback')
        
    from models import SellerFeedback
    fb = SellerFeedback(store_id=store.id, message=message)
    db.session.add(fb)
    db.session.commit()
    
    flash("Feedback submitted successfully. Thank you for helping us improve the website!", "success")
    return redirect(url_for('seller.dashboard') + '#feedback')

@seller_bp.route('/commission/pay', methods=['GET', 'POST'])
def pay_commission():
    store = current_user.store_profile
    commission_due = store.commission_due
    
    from models import SystemSetting
    admin_upi_setting = SystemSetting.query.filter_by(key='ADMIN_UPI_ID').first()
    if not admin_upi_setting:
        admin_upi_setting = SystemSetting.query.filter_by(key='admin_upi_id').first()
    admin_upi = admin_upi_setting.value if admin_upi_setting else "admin@upi"
    
    admin_qr_setting = SystemSetting.query.filter_by(key='ADMIN_QR_CODE').first()
    admin_qr_code = admin_qr_setting.value if admin_qr_setting else None
    
    import urllib.parse
    upi_uri = f"upi://pay?pa={admin_upi}&pn=VKshop_Platform_Admin&am={commission_due}&tn=COMM-{store.id}&cu=INR"
    qr_api_url = f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data={urllib.parse.quote(upi_uri)}"
    
    if request.method == 'POST':
        utr = request.form.get('utr_number', '').strip()
        contact = request.form.get('contact_number', '').strip()
        description = request.form.get('description', '').strip()
        screenshot_file = request.files.get('screenshot')
        
        if not utr or not contact or not screenshot_file:
            flash("UTR number, contact number, and screenshot are required.", "danger")
            return redirect(request.referrer or url_for('seller.pay_commission'))
            
        from services.storage import upload_file_field
        key, err = upload_file_field(screenshot_file, 'commission', is_private=True)
        if err:
            flash(f"Failed to upload payment proof screenshot: {err}", "danger")
            return redirect(request.referrer or url_for('seller.pay_commission'))
        fn_screenshot = key
        
        from models import CommissionPayment
        cp = CommissionPayment(
            store_id=store.id,
            amount=commission_due,
            screenshot=fn_screenshot,
            transaction_id=utr,
            contact_number=contact,
            description=description,
            status='In progress'
        )
        db.session.add(cp)
        
        store.commission_payment_status = 'Submitted'
        store.commission_requested_at = datetime.utcnow()
        db.session.commit()
        
        # Notify admin via Socket.IO
        try:
            from app import emit_commission_update
            emit_commission_update(store.id, 'Submitted', commission_due)
        except Exception:
            pass
        
        flash("Commission payment proof submitted! Awaiting Admin verification.", "success")
        return redirect(url_for('seller.dashboard') + '#commission')
        
    return render_template(
        'seller/pay_commission.html',
        store=store,
        commission_due=commission_due,
        admin_upi=admin_upi,
        qr_api_url=qr_api_url,
        upi_uri=upi_uri,
        admin_qr_code=admin_qr_code
    )

# ==================== COMMISSION REPORT ====================

@seller_bp.route('/commission/report', methods=['GET', 'POST'])
def commission_report():
    """Seller can report/complain about a commission payment."""
    store = current_user.store_profile
    
    if request.method == 'POST':
        commission_payment_id = request.form.get('commission_payment_id', type=int)
        explanation = request.form.get('explanation', '').strip()
        proof_file = request.files.get('proof_file')
        
        if not explanation:
            flash("Please provide an explanation for your report.", "danger")
            return redirect(request.referrer or url_for('seller.commission_report'))
        
        fn_proof = None
        if proof_file and proof_file.filename:
            from services.storage import upload_file_field
            key, err = upload_file_field(proof_file, 'commission-reports', is_private=True)
            if err:
                flash(f"Failed to upload proof file: {err}", "danger")
                return redirect(request.referrer or url_for('seller.commission_report'))
            fn_proof = key
        
        from models import CommissionReport
        report = CommissionReport(
            store_id=store.id,
            commission_payment_id=commission_payment_id,
            explanation=explanation,
            proof_file=fn_proof,
            status='Open'
        )
        db.session.add(report)
        db.session.commit()
        
        log_audit("SUBMIT_COMMISSION_REPORT", f"Submitted commission report for store: {store.name}")
        flash("Your commission report has been submitted. Admin will review it shortly.", "success")
        return redirect(url_for('seller.dashboard') + '#commission')
    
    from models import CommissionPayment
    payments = CommissionPayment.query.filter_by(store_id=store.id).order_by(CommissionPayment.created_at.desc()).all()
    
    from models import CommissionReport
    reports = CommissionReport.query.filter_by(store_id=store.id).order_by(CommissionReport.created_at.desc()).all()
    
    return render_template('seller/commission_report.html', payments=payments, reports=reports)

# ==================== STORE ANALYTICS - DOWNLOAD CHARTS ====================

@seller_bp.route('/analytics/download/weekly-sales')
def download_weekly_sales_chart():
    """Download weekly sales chart as PNG or PDF."""
    store = current_user.store_profile
    from datetime import timedelta
    
    today = datetime.utcnow()
    week_offset = request.args.get('week_offset', 0, type=int)
    start_of_week = today - timedelta(days=today.weekday()) - timedelta(weeks=week_offset)
    
    week_sales_labels = []
    week_sales_data = []
    week_day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    
    for i in range(7):
        day_start = start_of_week + timedelta(days=i)
        day_end = day_start + timedelta(days=1)
        day_sales = db.session.query(db.func.coalesce(db.func.sum(OrderItem.total_price), 0)).join(
            Order, OrderItem.order_id == Order.id
        ).join(
            Product, OrderItem.product_id == Product.id
        ).filter(
            Product.seller_id == store.id,
            Order.created_at >= day_start,
            Order.created_at < day_end,
            Order.status.in_(['Confirmed', 'Packed', 'Shipped', 'Out For Delivery', 'Delivered'])
        ).scalar()
        week_sales_labels.append(week_day_names[i])
        week_sales_data.append(float(day_sales))
    
    total_weekly_sales = sum(week_sales_data)
    
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import io
    
    fig, ax = plt.subplots(figsize=(10, 5))
    colors = ['#2563eb'] * len(week_sales_labels)
    ax.bar(week_sales_labels, week_sales_data, color=colors)
    ax.set_title(f'Weekly Sales (INR) - Week starting {start_of_week.strftime("%d %b %Y")}')
    ax.set_ylabel('Sales (INR)')
    ax.set_xlabel('Day')
    
    for i, v in enumerate(week_sales_data):
        ax.text(i, v + max(week_sales_data)*0.01 if max(week_sales_data) > 0 else 1, f'₹{v:.0f}', ha='center', fontsize=9)
    
    plt.tight_layout()
    
    format_type = request.args.get('format', 'png')
    
    if format_type == 'pdf':
        pdf_buffer = io.BytesIO()
        fig.savefig(pdf_buffer, format='pdf', dpi=150)
        plt.close(fig)
        pdf_buffer.seek(0)
        return send_file(
            pdf_buffer,
            as_attachment=True,
            download_name=f'Weekly_Sales_{start_of_week.strftime("%Y%m%d")}.pdf',
            mimetype='application/pdf'
        )
    else:
        img_buffer = io.BytesIO()
        fig.savefig(img_buffer, format='png', dpi=150)
        plt.close(fig)
        img_buffer.seek(0)
        return send_file(
            img_buffer,
            as_attachment=True,
            download_name=f'Weekly_Sales_{start_of_week.strftime("%Y%m%d")}.png',
            mimetype='image/png'
        )

@seller_bp.route('/analytics/api/weekly-sales')
def api_weekly_sales():
    """API endpoint for weekly sales data (for real-time updates)."""
    store = current_user.store_profile
    from datetime import timedelta
    
    week_offset = request.args.get('week_offset', 0, type=int)
    today = datetime.utcnow()
    start_of_week = today - timedelta(days=today.weekday()) - timedelta(weeks=week_offset)
    
    week_sales_labels = []
    week_sales_data = []
    week_day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    
    for i in range(7):
        day_start = start_of_week + timedelta(days=i)
        day_end = day_start + timedelta(days=1)
        day_sales = db.session.query(db.func.coalesce(db.func.sum(OrderItem.total_price), 0)).join(
            Order, OrderItem.order_id == Order.id
        ).join(
            Product, OrderItem.product_id == Product.id
        ).filter(
            Product.seller_id == store.id,
            Order.created_at >= day_start,
            Order.created_at < day_end,
            Order.status.in_(['Confirmed', 'Packed', 'Shipped', 'Out For Delivery', 'Delivered'])
        ).scalar()
        week_sales_labels.append(week_day_names[i])
        week_sales_data.append(float(day_sales))
    
    return jsonify({
        'labels': week_sales_labels,
        'data': week_sales_data,
        'total': sum(week_sales_data),
        'week_start': start_of_week.strftime('%Y-%m-%d')
    })