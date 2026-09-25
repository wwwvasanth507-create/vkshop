from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, current_app
from flask_login import login_required, current_user
from database import db
from models import (User, Address, Order, OrderItem, Product, ProductVariant, 
                    CartItem, Wishlist, Coupon, WalletTransaction, RewardPoint, 
                    SupportTicket, SupportMessage, Payment, ReturnRequest, Refund, StoreProfile)
from services.payment import PaymentGateway
from services.invoice import InvoiceService
import uuid
from datetime import datetime

customer_bp = Blueprint('customer', __name__)

# Middleware to restrict routes to Customer role only
@customer_bp.before_request
@login_required
def check_customer_role():
    if current_user.role != 'customer' and current_user.role != 'admin':
        flash("Unauthorized area. Customers only.", "danger")
        return redirect(url_for('main.index'))

def populate_visible_status(order):
    from routes.admin import get_setting
    enable_out_for_delivery = get_setting('ENABLE_OUT_FOR_DELIVERY', True)
    enable_delivered = get_setting('ENABLE_DELIVERED', True)
    
    status = order.status
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
                
    order.visible_status = status

@customer_bp.route('/customer/dashboard')
def dashboard():
    orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.created_at.desc()).all()
    for o in orders:
        populate_visible_status(o)
    addresses = Address.query.filter_by(user_id=current_user.id).all()
    tickets = SupportTicket.query.filter_by(user_id=current_user.id).order_by(SupportTicket.updated_at.desc()).all()
    points_txs = RewardPoint.query.filter_by(user_id=current_user.id).order_by(RewardPoint.created_at.desc()).all()
    wishlist = Wishlist.query.filter_by(user_id=current_user.id).all()
    
    return render_template(
        'customer/dashboard.html',
        orders=orders,
        addresses=addresses,
        tickets=tickets,
        points_txs=points_txs,
        wishlist=wishlist
    )

# ----------------- ADDRESS BOOK -----------------
@customer_bp.route('/address/add', methods=['POST'])
def add_address():
    title = request.form.get('title')
    fullName = request.form.get('fullName')
    addressLine1 = request.form.get('addressLine1')
    addressLine2 = request.form.get('addressLine2')
    city = request.form.get('city')
    state = request.form.get('state')
    postalCode = request.form.get('postalCode')
    phone = request.form.get('phone')
    is_default = True if request.form.get('is_default') else False
    
    # CID fields
    door_no = request.form.get('door_no', '').strip()
    street = request.form.get('street', '').strip()
    village_city = request.form.get('village_city', '').strip()
    post_name = request.form.get('post_name', '').strip()
    taluk_name = request.form.get('taluk_name', '').strip()
    district = request.form.get('district', '').strip()
    landmark = request.form.get('landmark', '').strip()
    contact_number = request.form.get('contact_number', '').strip()
    
    if is_default:
        # Reset existing defaults
        Address.query.filter_by(user_id=current_user.id).update({Address.is_default: False})
        
    addr = Address(
        user_id=current_user.id, title=title, fullName=fullName,
        addressLine1=addressLine1 or f"{door_no}, {street}", addressLine2=addressLine2 or landmark, city=city or village_city,
        state=state, postalCode=postalCode or request.form.get('pin_code'), phone=phone or contact_number, is_default=is_default,
        door_no=door_no, street=street, village_city=village_city, post_name=post_name,
        taluk_name=taluk_name, district=district, landmark=landmark, contact_number=contact_number
    )
    db.session.add(addr)
    db.session.commit()
    flash("Address added successfully.", "success")
    return redirect(url_for('customer.dashboard') + '#addresses')

@customer_bp.route('/address/edit/<int:addr_id>', methods=['GET', 'POST'])
def edit_address(addr_id):
    addr = Address.query.filter_by(id=addr_id, user_id=current_user.id).first_or_404()
    if request.method == 'POST':
        addr.title = request.form.get('title')
        addr.fullName = request.form.get('fullName')
        addr.addressLine1 = request.form.get('addressLine1') or f"{request.form.get('door_no')}, {request.form.get('street')}"
        addr.addressLine2 = request.form.get('addressLine2') or request.form.get('landmark')
        addr.city = request.form.get('city') or request.form.get('village_city')
        addr.state = request.form.get('state')
        addr.postalCode = request.form.get('postalCode') or request.form.get('pin_code')
        addr.phone = request.form.get('phone') or request.form.get('contact_number')
        addr.is_default = True if request.form.get('is_default') else False
        
        addr.door_no = request.form.get('door_no')
        addr.street = request.form.get('street')
        addr.village_city = request.form.get('village_city')
        addr.post_name = request.form.get('post_name')
        addr.taluk_name = request.form.get('taluk_name')
        addr.district = request.form.get('district')
        addr.landmark = request.form.get('landmark')
        addr.contact_number = request.form.get('contact_number')
        
        if addr.is_default:
            Address.query.filter(Address.id != addr_id, Address.user_id == current_user.id).update({Address.is_default: False})
            
        db.session.commit()
        flash("Address updated successfully.", "success")
        return redirect(url_for('customer.dashboard') + '#addresses')
        
    return render_template('customer/edit_address.html', addr=addr)

@customer_bp.route('/address/delete/<int:addr_id>')
def delete_address(addr_id):
    addr = Address.query.filter_by(id=addr_id, user_id=current_user.id).first_or_404()
    db.session.delete(addr)
    db.session.commit()
    flash("Address deleted successfully.", "success")
    return redirect(url_for('customer.dashboard') + '#addresses')

# ----------------- CART & WISHLIST -----------------
@customer_bp.route('/cart')
def view_cart():
    cart_items = CartItem.query.filter_by(user_id=current_user.id).all()
    
    # Calculate cart values
    subtotal = 0.0
    for item in cart_items:
        price = item.variant.price if item.variant else item.product.offer_price
        subtotal += price * item.quantity
        
    from routes.admin import get_setting
    tax_percent = get_setting('TAX_GST_PERCENTAGE', 18.0)
    ship_fee = get_setting('SHIPPING_FEE', 50.0)
    free_threshold = get_setting('FREE_SHIPPING_THRESHOLD', 500.0)
    
    tax = round(subtotal * (tax_percent / 100.0), 2)
    shipping = ship_fee if (subtotal < free_threshold and subtotal > 0.0) else 0.0
    total = round(subtotal + tax + shipping, 2)
    
    # Check for valid active coupons
    coupons = Coupon.query.filter(Coupon.expiry_date > datetime.utcnow(), Coupon.is_active == True).all()
    
    return render_template(
        'customer/cart.html',
        cart_items=cart_items,
        subtotal=subtotal,
        tax=tax,
        shipping=shipping,
        total=total,
        coupons=coupons,
        tax_percent=tax_percent
    )

@customer_bp.route('/cart/add', methods=['POST'])
def add_to_cart():
    product_id = request.form.get('product_id', type=int)
    variant_id = request.form.get('variant_id', type=int)
    qty = request.form.get('quantity', 1, type=int)
    
    product = Product.query.get_or_404(product_id)
    
    # Check if product is out of stock
    if product.is_out_of_stock:
        flash(f"Sorry, '{product.name}' is currently out of stock and cannot be added to cart.", "danger")
        return redirect(request.referrer)
    
    # Check variant stock if applicable
    if variant_id:
        variant = ProductVariant.query.filter_by(id=variant_id, product_id=product_id).first_or_404()
        if variant.stock < qty:
            flash(f"Insufficient stock. Only {variant.stock} available.", "danger")
            return redirect(request.referrer)
    
    # Check if item already exists in cart
    existing_item = CartItem.query.filter_by(
        user_id=current_user.id,
        product_id=product_id,
        variant_id=variant_id
    ).first()
    
    if existing_item:
        existing_item.quantity += qty
    else:
        new_item = CartItem(
            user_id=current_user.id,
            product_id=product_id,
            variant_id=variant_id,
            quantity=qty
        )
        db.session.add(new_item)
        
    db.session.commit()
    flash("Item added to cart.", "success")
    return redirect(request.referrer or url_for('customer.view_cart'))

@customer_bp.route('/cart/update/<int:item_id>', methods=['POST'])
def update_cart_item(item_id):
    item = CartItem.query.filter_by(id=item_id, user_id=current_user.id).first_or_404()
    qty = request.form.get('quantity', type=int)
    
    if qty <= 0:
        db.session.delete(item)
    else:
        # Check stock limits
        if item.variant:
            if item.variant.stock < qty:
                flash(f"Not enough stock. Max available: {item.variant.stock}.", "danger")
                return redirect(request.referrer or url_for('customer.view_cart'))
        item.quantity = qty
        
    db.session.commit()
    flash("Cart updated.", "success")
    return redirect(request.referrer or url_for('customer.view_cart'))

@customer_bp.route('/cart/remove/<int:item_id>')
def remove_cart_item(item_id):
    item = CartItem.query.filter_by(id=item_id, user_id=current_user.id).first_or_404()
    db.session.delete(item)
    db.session.commit()
    flash("Item removed from cart.", "success")
    return redirect(request.referrer or url_for('customer.view_cart'))

@customer_bp.route('/wishlist/add/<int:product_id>')
def add_to_wishlist(product_id):
    product = Product.query.get_or_404(product_id)
    existing = Wishlist.query.filter_by(user_id=current_user.id, product_id=product.id).first()
    
    if not existing:
        w = Wishlist(user_id=current_user.id, product_id=product.id)
        db.session.add(w)
        db.session.commit()
        flash("Added to wishlist.", "success")
    else:
        flash("Already in wishlist.", "info")
        
    return redirect(request.referrer)

@customer_bp.route('/wishlist/remove/<int:wish_id>')
def remove_from_wishlist(wish_id):
    w = Wishlist.query.filter_by(id=wish_id, user_id=current_user.id).first_or_404()
    db.session.delete(w)
    db.session.commit()
    flash("Removed from wishlist.", "success")
    return redirect(url_for('customer.dashboard') + '#wishlist')

# ----------------- CHECKOUT & ORDERS -----------------
@customer_bp.route('/checkout', methods=['GET', 'POST'])
def checkout():
    cart_items = CartItem.query.filter_by(user_id=current_user.id).all()
    if not cart_items:
        flash("Your cart is empty.", "warning")
        return redirect(request.referrer or url_for('customer.view_cart'))
        
    # Check if any seller is disabled
    for item in cart_items:
        if not item.product.store.user.is_active or item.product.store.status == 'Suspended':
            flash(f"Product '{item.product.name}' is from a seller who is currently not available. Please remove it from your cart.", "danger")
            return redirect(request.referrer or url_for('customer.view_cart'))

    addresses = Address.query.filter_by(user_id=current_user.id).all()
    
    # Calculate cart numbers
    subtotal = 0.0
    for item in cart_items:
        price = item.variant.price if item.variant else item.product.offer_price
        subtotal += price * item.quantity
        
    from routes.admin import get_setting
    tax_percent = get_setting('TAX_GST_PERCENTAGE', 18.0)
    ship_fee = get_setting('SHIPPING_FEE', 50.0)
    free_threshold = get_setting('FREE_SHIPPING_THRESHOLD', 500.0)
    enable_upi = get_setting('ENABLE_UPI', True)
    enable_cod = get_setting('ENABLE_COD', True)
    
    tax = round(subtotal * (tax_percent / 100.0), 2)
    shipping = ship_fee if subtotal < free_threshold else 0.0
    total = round(subtotal + tax + shipping, 2)
    
    coupon_code = request.form.get('coupon_code') or request.args.get('coupon_code')
    discount = 0.0
    coupon_obj = None
    
    if coupon_code:
        coupon_obj = Coupon.query.filter_by(code=coupon_code, is_active=True).first()
        if coupon_obj and coupon_obj.expiry_date > datetime.utcnow() and subtotal >= coupon_obj.min_order_amount:
            if coupon_obj.discount_type == 'flat':
                discount = min(coupon_obj.value, subtotal)
            elif coupon_obj.discount_type == 'percentage':
                discount = round(subtotal * (coupon_obj.value / 100.0), 2)
        else:
            flash("Invalid or expired coupon, or minimum amount not met.", "danger")
            
    grand_total = max(total - discount, 0.0)
    
    if request.method == 'POST' and 'place_order' in request.form:
        # ---- Out of stock check before placing order ----
        out_of_stock_items = []
        for item in cart_items:
            if item.product.is_out_of_stock or (item.variant and item.variant.stock <= 0):
                out_of_stock_items.append(item.product.name)
        if out_of_stock_items:
            names = ', '.join(out_of_stock_items)
            flash(f"Cannot place order. The following product(s) are out of stock: {names}. Please remove them from your cart.", "danger")
            return redirect(request.referrer or url_for('customer.view_cart'))

        addr_id = request.form.get('address_id', type=int)
        payment_method = request.form.get('payment_method')
        use_wallet = True if request.form.get('use_wallet') else False
        use_reward = True if request.form.get('use_reward') else False
        
        # Check payment method enforcement
        if payment_method == 'UPI' and not enable_upi:
            flash("UPI payment method is currently disabled.", "danger")
            return redirect(url_for('customer.checkout', coupon_code=coupon_code))
        if payment_method == 'COD' and not enable_cod:
            flash("Cash on Delivery is currently disabled.", "danger")
            return redirect(url_for('customer.checkout', coupon_code=coupon_code))
        if payment_method not in ['UPI', 'COD'] and not (use_wallet or use_reward):
            flash("Unsupported payment method selected.", "danger")
            return redirect(url_for('customer.checkout', coupon_code=coupon_code))
            
        if not addr_id:
            flash("Please select a delivery address.", "danger")
            return redirect(url_for('customer.checkout', coupon_code=coupon_code))

        # ---- Region availability check ----
        selected_address = Address.query.filter_by(id=addr_id, user_id=current_user.id).first()
        if not selected_address:
            flash("Invalid address selected.", "danger")
            return redirect(url_for('customer.checkout', coupon_code=coupon_code))

        unavailable_products = []
        for item in cart_items:
            if not item.product.is_available_in_address(selected_address):
                unavailable_products.append(item.product.name)

        if unavailable_products:
            names = ', '.join(unavailable_products)
            flash(
                f"The following product(s) are currently unavailable in your address: {names}. "
                f"Please remove them from your cart or choose a different address.",
                "danger"
            )
            return redirect(url_for('customer.checkout', coupon_code=coupon_code))
            
        # Wallet and Rewards calculations
        wallet_deduction = 0.0
        if use_wallet:
            balance = current_user.wallet_balance
            wallet_deduction = min(balance, grand_total)
            grand_total -= wallet_deduction
            
        reward_deduction = 0.0
        if use_reward:
            pts = current_user.reward_points_balance
            # 1 reward point = 1 INR
            reward_deduction = min(float(pts), grand_total)
            grand_total -= reward_deduction
            
        # Process Gateway transaction if grand_total > 0
        tx_id = f"TXN-{uuid.uuid4().hex[:10].upper()}"
        payment_status = "Pending"
        is_upi_scan_pay = (payment_method == 'UPI' and grand_total > 0)
        
        if grand_total > 0:
            if is_upi_scan_pay:
                success = True
                tx_id = "Awaiting Verification"
                payment_status = "Awaiting Verification"
            else:
                pay_details = {}
                if payment_method in ['Credit Card', 'Debit Card']:
                    pay_details['card_number'] = request.form.get('card_number')
                    pay_details['cvv'] = request.form.get('cvv')
                elif payment_method == 'Net Banking':
                    pay_details['bank_name'] = request.form.get('bank_name')
                    
                success, tx_id, msg = PaymentGateway.process_payment(payment_method, grand_total, pay_details)
                if not success:
                    flash(f"Payment failed: {msg}", "danger")
                    return redirect(url_for('customer.checkout', coupon_code=coupon_code))
                payment_status = "Completed" if payment_method != 'COD' else "Pending"
        else:
            # Paid fully via Wallet/Rewards
            payment_method = "Points/Wallet"
            payment_status = "Completed"
            
        # Complete deductions
        if wallet_deduction > 0:
            w_tx = WalletTransaction(
                user_id=current_user.id,
                amount=wallet_deduction,
                type='debit',
                description="Order Checkout deduction"
            )
            db.session.add(w_tx)
            
        if reward_deduction > 0:
            r_tx = RewardPoint(
                user_id=current_user.id,
                points=int(reward_deduction),
                type='debit',
                description="Order Checkout points redeem"
            )
            db.session.add(r_tx)
            
        # Create Order
        order_num = f"ORD-{uuid.uuid4().hex[:8].upper()}"
        new_order = Order(
            order_number=order_num,
            user_id=current_user.id,
            address_id=addr_id,
            total_amount=subtotal,
            discount_amount=discount,
            shipping_charges=shipping,
            tax_amount=tax,
            grand_total=grand_total + wallet_deduction + reward_deduction, # Total value
            status="Pending" if is_upi_scan_pay else ("Confirmed" if payment_method != 'COD' else "Pending"),
            coupon_id=coupon_obj.id if coupon_obj else None,
            wallet_deduction=wallet_deduction,
            reward_points_deduction=reward_deduction,
            tracking_number=f"TRK-{uuid.uuid4().hex[:10].upper()}",
            courier_partner="VKshop Logistics"
        )
        db.session.add(new_order)
        db.session.commit()
        
        # Create Order Items and decrease stock
        for item in cart_items:
            unit_p = item.variant.price if item.variant else item.product.offer_price
            tot_p = unit_p * item.quantity
            
            var_details = f"Color: {item.variant.color}, Size: {item.variant.size}" if item.variant else None
            
            ord_item = OrderItem(
                order_id=new_order.id,
                product_id=item.product_id,
                variant_id=item.variant_id,
                quantity=item.quantity,
                unit_price=unit_p,
                total_price=tot_p,
                product_name=item.product.name,
                variant_details=var_details
            )
            db.session.add(ord_item)
            
            # Decrease stock
            if item.variant:
                item.variant.stock = max(item.variant.stock - item.quantity, 0)
            else:
                # No variant — reduce base product stock
                item.product.stock = max(item.product.stock - item.quantity, 0)
                
            # Distribute earnings to seller only if payment is confirmed immediately (Wallet, Card, Points)
            if not is_upi_scan_pay:
                seller = StoreProfile.query.get(item.product.seller_id)
                if seller:
                    seller.balance += tot_p
                    seller.total_sales += tot_p
                
            # Delete from persistent cart
            db.session.delete(item)
            
        # Record Payment
        pmt = Payment(
            order_id=new_order.id,
            payment_method=payment_method,
            transaction_id=tx_id,
            status=payment_status,
            amount=grand_total
        )
        db.session.add(pmt)
        
        # Award reward points only for confirmed immediate payments
        if not is_upi_scan_pay:
            earned_pts = int(subtotal / 100)
            if earned_pts > 0:
                db.session.add(RewardPoint(
                    user_id=current_user.id,
                    points=earned_pts,
                    type='credit',
                    description="Purchase reward points"
                ))
            
        db.session.commit()
        
        if is_upi_scan_pay:
            flash(f"Order {order_num} created! Please complete UPI payment.", "info")
            return redirect(url_for('customer.order_pay', order_id=new_order.id))
            
        flash(f"Order {order_num} placed successfully!", "success")
        return redirect(url_for('customer.order_detail', order_id=new_order.id))
        
    return render_template(
        'customer/checkout.html',
        cart_items=cart_items,
        addresses=addresses,
        subtotal=subtotal,
        tax=tax,
        shipping=shipping,
        discount=discount,
        coupon_code=coupon_code,
        grand_total=grand_total,
        wallet_balance=current_user.wallet_balance,
        reward_points=current_user.reward_points_balance,
        enable_upi=enable_upi,
        enable_cod=enable_cod,
        tax_percent=tax_percent
    )

@customer_bp.route('/order/<int:order_id>')
def order_detail(order_id):
    order = Order.query.filter_by(id=order_id, user_id=current_user.id).first_or_404()
    
    from routes.admin import get_setting
    enable_out_for_delivery = get_setting('ENABLE_OUT_FOR_DELIVERY', True)
    enable_delivered = get_setting('ENABLE_DELIVERED', True)
    
    statuses = ['Ordered', 'Confirmed', 'Shipped']
    if enable_out_for_delivery:
        statuses.append('Out For Delivery')
    if enable_delivered:
        statuses.append('Delivered')
        
    populate_visible_status(order)
    current_idx = statuses.index(order.visible_status) if order.visible_status in statuses else -1
    
    return render_template('customer/order_detail.html', order=order, statuses=statuses, current_idx=current_idx)

@customer_bp.route('/invoice/download/<int:order_id>')
def download_invoice(order_id):
    order = Order.query.filter_by(id=order_id, user_id=current_user.id).first_or_404()
    pdf_buffer = InvoiceService.generate_invoice_pdf(order)
    return send_file(
        pdf_buffer,
        as_attachment=True,
        download_name=f"Invoice_{order.order_number}.pdf",
        mimetype="application/pdf"
    )

# ----------------- RETURNS & REFUNDS -----------------
@customer_bp.route('/order/return/<int:item_id>', methods=['POST'])
def request_return(item_id):
    # Check if Return System is enabled
    from routes.admin import get_setting
    enable_returns = get_setting('ENABLE_RETURNS', True)
    if not enable_returns:
        flash("Return system is currently disabled by the admin.", "danger")
        return redirect(request.referrer)
    
    order_item = OrderItem.query.get_or_404(item_id)
    # Check ownership
    order = Order.query.get(order_item.order_id)
    if order.user_id != current_user.id:
        flash("Unauthorized return request.", "danger")
        return redirect(url_for('customer.dashboard') + '#orders')
        
    reason = request.form.get('reason', '').strip()
    if not reason:
        flash("Please provide a return reason.", "danger")
        return redirect(request.referrer)
        
    existing = ReturnRequest.query.filter_by(order_item_id=item_id).first()
    if existing:
        flash("Return request already submitted for this item.", "info")
        return redirect(request.referrer)
        
    ret = ReturnRequest(order_item_id=item_id, reason=reason, status='Pending')
    db.session.add(ret)
    db.session.commit()
    
    # Update order status to Return Initiated
    order.status = "Returned"
    db.session.commit()
    
    flash("Return request submitted successfully. A refund will be processed upon approval.", "success")
    return redirect(url_for('customer.dashboard') + '#orders')

# ----------------- SUPPORT TICKETS -----------------
@customer_bp.route('/tickets', methods=['GET', 'POST'])
def support_tickets():
    if request.method == 'POST':
        subject = request.form.get('subject', '').strip()
        category = request.form.get('category', 'General')
        priority = request.form.get('priority', 'Medium')
        description = request.form.get('description', '').strip()
        
        if not subject or not description:
            flash("Subject and description cannot be empty.", "danger")
            return redirect(request.referrer or url_for('customer.support_tickets'))
            
        ticket = SupportTicket(
            user_id=current_user.id,
            subject=subject,
            category=category,
            priority=priority,
            description=description,
            status='Open'
        )
        db.session.add(ticket)
        db.session.commit()
        
        # Add the initial message
        msg = SupportMessage(ticket_id=ticket.id, user_id=current_user.id, message=description, is_admin=False)
        db.session.add(msg)
        db.session.commit()
        
        from services.email_service import EmailService
        EmailService.send_mock_support_email(
            current_user.email,
            f"Support Ticket #{ticket.id} Opened: {subject}",
            f"We have received your support request:\n\n{description}"
        )
        
        flash("Support ticket opened successfully. We will get back to you shortly.", "success")
        return redirect(url_for('customer.dashboard') + '#tickets')
        
    tickets = SupportTicket.query.filter_by(user_id=current_user.id).order_by(SupportTicket.created_at.desc()).all()
    return render_template('customer/tickets.html', tickets=tickets)

@customer_bp.route('/ticket/<int:ticket_id>', methods=['GET', 'POST'])
def view_ticket(ticket_id):
    ticket = SupportTicket.query.filter_by(id=ticket_id, user_id=current_user.id).first_or_404()
    
    if request.method == 'POST':
        message = request.form.get('message', '').strip()
        if message:
            msg = SupportMessage(ticket_id=ticket.id, user_id=current_user.id, message=message, is_admin=False)
            ticket.status = "Open"  # Reopen or keep active on customer message
            db.session.add(msg)
            db.session.commit()
            
            from services.email_service import EmailService
            EmailService.send_mock_support_email(
                current_user.email,
                f"New Reply on Support Ticket #{ticket.id}",
                f"You have added a new message to your support ticket:\n\n{message}"
            )
            
            flash("Message added.", "success")
            return redirect(url_for('customer.view_ticket', ticket_id=ticket.id))
            
    return render_template('customer/ticket_detail.html', ticket=ticket)

# ----------------- WALLET TOPUP -----------------
@customer_bp.route('/wallet/topup', methods=['POST'])
@login_required
def wallet_topup():
    amount_str = request.form.get('amount', '0').strip()
    try:
        amount = float(amount_str)
        if amount <= 0:
            flash("Please enter a valid top-up amount greater than 0.", "danger")
            return redirect(url_for('customer.dashboard') + '#points')
    except ValueError:
        flash("Invalid amount entered.", "danger")
        return redirect(url_for('customer.dashboard') + '#points')
        
    w_tx = WalletTransaction(
        user_id=current_user.id,
        amount=amount,
        type='credit',
        description=f"Wallet Topup via Direct Credit"
    )
    db.session.add(w_tx)
    db.session.commit()
    
    flash(f"Successfully added INR {amount:.2f} to your wallet balance!", "success")
    return redirect(url_for('customer.dashboard') + '#points')

@customer_bp.route('/order/pay/<int:order_id>', methods=['GET', 'POST'])
def order_pay(order_id):
    order = Order.query.filter_by(id=order_id, user_id=current_user.id).first_or_404()
    payment = Payment.query.filter_by(order_id=order.id).first_or_404()
    
    first_item = order.items[0]
    seller = StoreProfile.query.get(first_item.product.seller_id)
    
    upi_id = seller.upi_id if (seller and seller.upi_id) else "admin@upi"
    seller_qr = seller.qr_code_path if (seller and seller.qr_code_path) else None
    
    import urllib.parse
    encoded_name = urllib.parse.quote(seller_name)
    upi_uri = f"upi://pay?pa={upi_id}&pn={encoded_name}&am={payment.amount}&tn={order.order_number}&cu=INR"
    
    qr_api_url = f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data={urllib.parse.quote(upi_uri)}"
    
    if request.method == 'POST':
        utr = request.form.get('utr_number', '').strip()
        contact = request.form.get('contact_number', '').strip()
        description = request.form.get('description', '').strip()
        screenshot_file = request.files.get('screenshot')
        
        if not utr or not contact or not screenshot_file:
            flash("UTR number, contact number, and payment screenshot are required.", "danger")
            return redirect(url_for('customer.order_pay', order_id=order.id))
            
        from werkzeug.utils import secure_filename
        from config import Config
        import os
        
        os.makedirs(Config.USER_UPLOADS, exist_ok=True)
        fn_screenshot = secure_filename(f"payment_{order.order_number}_{screenshot_file.filename}")
        screenshot_file.save(os.path.join(Config.USER_UPLOADS, fn_screenshot))
        
        payment.transaction_id = utr
        payment.contact_number = contact
        payment.description = description
        payment.screenshot_path = fn_screenshot
        payment.status = "Awaiting Verification"
        
        order.status = "Pending"
        db.session.commit()
        
        flash("Payment proof submitted successfully! The seller's payment verifier will review it shortly.", "success")
        return redirect(url_for('customer.order_detail', order_id=order.id))
        
    return render_template(
        'customer/pay.html',
        order=order,
        upi_id=upi_id,
        seller_name=seller_name,
        seller_qr=seller_qr,
        qr_api_url=qr_api_url,
        upi_uri=upi_uri
    )

@customer_bp.route('/order/complaint/<int:order_id>', methods=['GET', 'POST'])
def file_complaint(order_id):
    order = Order.query.filter_by(id=order_id, user_id=current_user.id).first_or_404()
    if request.method == 'POST':
        details = request.form.get('details', '').strip()
        screenshot_file = request.files.get('screenshot')
        
        if not details:
            flash("Please provide details of the complaint.", "danger")
            return redirect(url_for('customer.file_complaint', order_id=order.id))
            
        from werkzeug.utils import secure_filename
        from config import Config
        import os
        
        fn_screenshot = None
        if screenshot_file and screenshot_file.filename:
            os.makedirs(Config.USER_UPLOADS, exist_ok=True)
            fn_screenshot = secure_filename(f"complaint_{order.order_number}_{screenshot_file.filename}")
            screenshot_file.save(os.path.join(Config.USER_UPLOADS, fn_screenshot))
            
        from models import Complaint
        comp = Complaint(
            user_id=current_user.id,
            order_id=order.id,
            screenshot=fn_screenshot,
            details=details,
            status='Pending'
        )
        db.session.add(comp)
        db.session.commit()
        
        flash("Your complaint has been submitted to the Admin. We will review it shortly.", "success")
        return redirect(url_for('customer.order_detail', order_id=order.id))
        
    return render_template('customer/file_complaint.html', order=order)
