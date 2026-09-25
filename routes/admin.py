from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_login import login_required, current_user
from database import db
from models import (User, StoreProfile, Category, Brand, Product, Order, OrderItem, Address,
                    Payment, Coupon, Review, SupportTicket, SupportMessage, Banner, 
                    ReturnRequest, Refund, AuditLog, SystemSetting, WalletTransaction,
                    CommissionPayment, Complaint, CommissionReport, SubAdminActivity,
                    SellerFeedback, SellerNotice)
from services.backup import BackupService
import os
import uuid
from datetime import datetime

admin_bp = Blueprint('admin', __name__)

def is_admin_or_sub_admin():
    return current_user.role in ['admin', 'sub_admin']

@admin_bp.before_request
@login_required
def check_admin_role():
    if current_user.role not in ['admin', 'sub_admin']:
        flash("Unauthorized access. Admins only.", "danger")
        return redirect(url_for('main.index'))

def log_audit(action, details=None):
    from routes.auth import log_audit as core_log
    core_log(current_user, action, details)

def get_setting(key, default):
    from models import SystemSetting
    s = SystemSetting.query.filter_by(key=key).first()
    if s:
        try:
            if isinstance(default, bool):
                return s.value.lower() == 'true'
            if isinstance(default, float):
                return float(s.value)
            if isinstance(default, int):
                return int(float(s.value))
            return s.value
        except ValueError:
            return default
    return default

def emit_socket_event(event, data):
    """Emit a Socket.IO event from admin routes."""
    try:
        from app import socketio
        socketio.emit(event, data)
    except Exception:
        pass  # SocketIO may not be available in all contexts

def notify_user(user_id, title, message, type='general'):
    """Disabled globally per user request."""
    pass

@admin_bp.route('/dashboard')
def dashboard():
    # Sub Admin check for Global Settings - hide from view
    if current_user.role == 'sub_admin':
        # Check if sub admin is blocked/deleted
        if not current_user.is_active:
            flash("Your account has been blocked. Contact Main Admin.", "danger")
            from flask_login import logout_user
            logout_user()
            return redirect(url_for('auth.login'))

    users_count = User.query.count()
    sellers_count = User.query.filter_by(role='seller').count()
    products_count = Product.query.count()
    orders = Order.query.all()
    
    # Calculate Sales Volume using verified/confirmed orders only
    sales_volume = sum(o.grand_total for o in orders if o.status in ['Confirmed', 'Packed', 'Shipped', 'Out For Delivery', 'Delivered'])
    orders_count_count = len([o for o in orders if o.status in ['Confirmed', 'Packed', 'Shipped', 'Out For Delivery', 'Delivered']])
    
    # Active tickets, returns
    pending_returns = ReturnRequest.query.filter_by(status='Pending').all()
    open_tickets = SupportTicket.query.filter(SupportTicket.status != 'Closed').all()
    pending_sellers = StoreProfile.query.filter_by(status='Pending').all()
    
    # Day-wise and Month-wise sales calculations
    import calendar
    from collections import defaultdict
    
    now = datetime.utcnow()
    current_year = now.year
    current_month = now.month
    
    start_of_month = datetime(current_year, current_month, 1)
    if current_month == 12:
        end_of_month = datetime(current_year + 1, 1, 1)
    else:
        end_of_month = datetime(current_year, current_month + 1, 1)
        
    confirmed_orders_month = Order.query.filter(
        Order.status.in_(['Confirmed', 'Packed', 'Shipped', 'Out For Delivery', 'Delivered']),
        Order.created_at >= start_of_month,
        Order.created_at < end_of_month
    ).all()
    
    num_days = calendar.monthrange(current_year, current_month)[1]
    day_sales = {day: 0.0 for day in range(1, num_days + 1)}
    for o in confirmed_orders_month:
        day_sales[o.created_at.day] += o.grand_total
        
    day_labels = [f"{day}" for day in range(1, num_days + 1)]
    day_data = [day_sales[day] for day in range(1, num_days + 1)]
    current_month_name = calendar.month_name[current_month]
    
    month_sales = {m: 0.0 for m in range(1, 13)}
    confirmed_orders_year = Order.query.filter(
        Order.status.in_(['Confirmed', 'Packed', 'Shipped', 'Out For Delivery', 'Delivered']),
        Order.created_at >= datetime(current_year, 1, 1),
        Order.created_at < datetime(current_year + 1, 1, 1)
    ).all()
    
    for o in confirmed_orders_year:
        month_sales[o.created_at.month] += o.grand_total
        
    month_labels = [calendar.month_abbr[m] for m in range(1, 13)]
    month_data = [month_sales[m] for m in range(1, 13)]

    # Commission payments - show ALL including 'In progress' (not auto-hidden)
    all_sellers = StoreProfile.query.all()
    pending_commission_payments = CommissionPayment.query.filter(
        CommissionPayment.status.in_(['In progress', 'Waiting for Verification'])
    ).all()
    all_commission_payments = CommissionPayment.query.order_by(CommissionPayment.created_at.desc()).all()
    complaints = Complaint.query.filter_by(status='Pending').all()
    
    categories = Category.query.all()
    brands = Brand.query.all()
    banners = Banner.query.order_by(Banner.order_seq).all()
    backups = BackupService.list_backups()
    
    # Commission Reports count
    open_commission_reports = CommissionReport.query.filter_by(status='Open').count()
    
    # Unread feedbacks count
    unread_feedbacks_count = SellerFeedback.query.filter_by(is_read=False).count()
    
    # All notices
    notices = SellerNotice.query.order_by(SellerNotice.created_at.desc()).all()
    
    # Sub Admins count (for main admin only)
    sub_admins = []
    if current_user.role == 'admin':
        sub_admins = User.query.filter_by(role='sub_admin').all()
    
    return render_template(
        'admin/dashboard.html',
        users_count=users_count,
        sellers_count=sellers_count,
        products_count=products_count,
        sales_volume=sales_volume,
        orders_count=orders_count_count,
        pending_returns=pending_returns,
        open_tickets=open_tickets,
        pending_sellers=pending_sellers,
        all_sellers=all_sellers,
        pending_commission_payments=pending_commission_payments,
        complaints=complaints,
        categories=categories,
        brands=brands,
        banners=banners,
        backups=backups,
        day_labels=day_labels,
        day_data=day_data,
        month_labels=month_labels,
        month_data=month_data,
        current_month_name=current_month_name,
        all_commission_payments=all_commission_payments,
        open_commission_reports=open_commission_reports,
        unread_feedbacks_count=unread_feedbacks_count,
        notices=notices,
        sub_admins=sub_admins,
        is_main_admin=current_user.role == 'admin'
    )

# ==================== SUB ADMIN MANAGEMENT (Main Admin only) ====================

@admin_bp.route('/sub-admin/create', methods=['POST'])
def create_sub_admin():
    if current_user.role != 'admin':
        flash("Only Main Admin can manage Sub Admins.", "danger")
        return redirect(url_for('admin.dashboard') + '#sub-admins')
    
    username = request.form.get('username', '').strip()
    email = request.form.get('email', '').strip()
    password = request.form.get('password', '')
    
    if not username or not email or not password:
        flash("All fields are required.", "danger")
        return redirect(url_for('admin.dashboard') + '#sub-admins')
    
    if len(password) < 6:
        flash("Password must be at least 6 characters.", "danger")
        return redirect(url_for('admin.dashboard') + '#sub-admins')
    
    if User.query.filter((User.username == username) | (User.email == email)).first():
        flash("Username or Email already exists.", "danger")
        return redirect(url_for('admin.dashboard') + '#sub-admins')
    
    sub_admin = User(username=username, email=email, role='sub_admin', is_active=True)
    sub_admin.set_password(password)
    db.session.add(sub_admin)
    db.session.commit()
    
    log_audit("CREATE_SUB_ADMIN", f"Created Sub Admin: {username} ({email})")
    flash(f"Sub Admin '{username}' created successfully.", "success")
    return redirect(url_for('admin.dashboard') + '#sub-admins')

@admin_bp.route('/sub-admin/edit/<int:user_id>', methods=['POST'])
def edit_sub_admin(user_id):
    if current_user.role != 'admin':
        flash("Only Main Admin can manage Sub Admins.", "danger")
        return redirect(url_for('admin.dashboard') + '#sub-admins')
    
    user = User.query.get_or_404(user_id)
    if user.role != 'sub_admin':
        flash("Invalid user.", "danger")
        return redirect(url_for('admin.dashboard') + '#sub-admins')
    
    user.username = request.form.get('username', user.username).strip()
    user.email = request.form.get('email', user.email).strip()
    password = request.form.get('password', '')
    
    if password:
        if len(password) < 6:
            flash("Password must be at least 6 characters.", "danger")
            return redirect(url_for('admin.dashboard') + '#sub-admins')
        user.set_password(password)
    
    db.session.commit()
    log_audit("EDIT_SUB_ADMIN", f"Edited Sub Admin: {user.username}")
    flash("Sub Admin updated successfully.", "success")
    return redirect(url_for('admin.dashboard') + '#sub-admins')

@admin_bp.route('/sub-admin/toggle/<int:user_id>')
def toggle_sub_admin(user_id):
    if current_user.role != 'admin':
        flash("Only Main Admin can manage Sub Admins.", "danger")
        return redirect(url_for('admin.dashboard') + '#sub-admins')
    
    user = User.query.get_or_404(user_id)
    if user.role != 'sub_admin':
        flash("Invalid user.", "danger")
        return redirect(url_for('admin.dashboard') + '#sub-admins')
    
    user.is_active = not user.is_active
    db.session.commit()
    
    status = "blocked" if not user.is_active else "unblocked"
    log_audit("TOGGLE_SUB_ADMIN", f"{status.capitalize()} Sub Admin: {user.username}")
    flash(f"Sub Admin '{user.username}' has been {status}.", "success")
    
    # Log SubAdminActivity
    activity = SubAdminActivity(
        user_id=user.id,
        action=f"Account {status} by Main Admin",
        details=f"Sub Admin account {status} by {current_user.username}",
        ip_address=request.remote_addr
    )
    db.session.add(activity)
    db.session.commit()
    
    # Notify sub admin if blocked
    if not user.is_active:
        notify_user(user.id, "Account Blocked", "Your Sub Admin account has been blocked by the Main Admin. Please contact support.", "alert")
        # Force logout via Socket.IO
        try:
            from app import emit_force_logout
            emit_force_logout(user.id, "Your Sub Admin account has been blocked by the Main Admin.")
        except Exception:
            pass
    
    return redirect(url_for('admin.dashboard') + '#sub-admins')

@admin_bp.route('/sub-admin/delete/<int:user_id>')
def delete_sub_admin(user_id):
    if current_user.role != 'admin':
        flash("Only Main Admin can manage Sub Admins.", "danger")
        return redirect(url_for('admin.dashboard') + '#sub-admins')
    
    user = User.query.get_or_404(user_id)
    if user.role != 'sub_admin':
        flash("Invalid user.", "danger")
        return redirect(url_for('admin.dashboard') + '#sub-admins')
    
    username = user.username
    
    # Log SubAdminActivity before deletion
    activity = SubAdminActivity(
        user_id=user.id,
        action="Account deleted by Main Admin",
        details=f"Sub Admin account deleted by {current_user.username}",
        ip_address=request.remote_addr
    )
    db.session.add(activity)
    
    # Force logout via Socket.IO before deleting
    try:
        from app import emit_force_logout
        emit_force_logout(user.id, "Your Sub Admin account has been deleted by the Main Admin.")
    except Exception:
        pass
    
    db.session.delete(user)
    db.session.commit()
    
    log_audit("DELETE_SUB_ADMIN", f"Deleted Sub Admin: {username}")
    flash("Sub Admin deleted successfully.", "success")
    return redirect(url_for('admin.dashboard') + '#sub-admins')

@admin_bp.route('/sub-admin/reset-password/<int:user_id>', methods=['POST'])
def reset_sub_admin_password(user_id):
    if current_user.role != 'admin':
        flash("Only Main Admin can manage Sub Admins.", "danger")
        return redirect(url_for('admin.dashboard') + '#sub-admins')
    
    user = User.query.get_or_404(user_id)
    if user.role != 'sub_admin':
        flash("Invalid user.", "danger")
        return redirect(url_for('admin.dashboard') + '#sub-admins')
    
    new_password = request.form.get('new_password', '')
    if len(new_password) < 6:
        flash("Password must be at least 6 characters.", "danger")
        return redirect(url_for('admin.dashboard') + '#sub-admins')
    
    user.set_password(new_password)
    db.session.commit()
    
    log_audit("RESET_SUB_ADMIN_PASSWORD", f"Reset password for Sub Admin: {user.username}")
    flash("Password reset successfully.", "success")
    return redirect(url_for('admin.dashboard') + '#sub-admins')

# ==================== ADMIN PASSWORD MANAGEMENT ====================

@admin_bp.route('/admin/password', methods=['GET', 'POST'])
def manage_admin_passwords():
    if current_user.role != 'admin':
        flash("Only Main Admin can change passwords.", "danger")
        return redirect(request.referrer or url_for('admin.dashboard'))
    
    if request.method == 'POST':
        target_user_id = request.form.get('user_id', type=int)
        new_password = request.form.get('new_password', '')
        
        if len(new_password) < 6:
            flash("Password must be at least 6 characters.", "danger")
            return redirect(request.referrer or url_for('admin.manage_admin_passwords'))
        
        target_user = User.query.get_or_404(target_user_id)
        if target_user.role not in ['admin', 'sub_admin']:
            flash("Invalid target user.", "danger")
            return redirect(request.referrer or url_for('admin.manage_admin_passwords'))
        
        target_user.set_password(new_password)
        db.session.commit()
        
        log_audit("ADMIN_PASSWORD_CHANGE", f"Changed password for {target_user.role}: {target_user.username}")
        flash(f"Password updated for {target_user.username}.", "success")
        return redirect(request.referrer or url_for('admin.manage_admin_passwords'))
    
    admins = User.query.filter(User.role.in_(['admin', 'sub_admin'])).all()
    return render_template('admin/passwords.html', admins=admins)

# ==================== COMMISSION REPORTS (Seller Reports) ====================

@admin_bp.route('/commission-reports')
def view_commission_reports():
    reports = CommissionReport.query.order_by(CommissionReport.created_at.desc()).all()
    return render_template('admin/commission_reports.html', reports=reports)

@admin_bp.route('/commission-report/reply/<int:report_id>', methods=['POST'])
def reply_commission_report(report_id):
    report = CommissionReport.query.get_or_404(report_id)
    reply = request.form.get('admin_reply', '').strip()
    
    if not reply:
        flash("Reply cannot be empty.", "danger")
        return redirect(request.referrer or url_for('admin.view_commission_reports'))
    
    report.admin_reply = reply
    report.status = 'Resolved'
    report.updated_at = datetime.utcnow()
    db.session.commit()
    
    log_audit("REPLY_COMMISSION_REPORT", f"Replied to commission report ID: {report_id}")
    
    # Notify seller
    store_user = User.query.filter_by(id=report.store.user_id).first()
    if store_user:
        notify_user(store_user.id, "Commission Report Update", 
                    f"Admin has replied to your commission report. Please check your dashboard.", "alert")
    
    flash("Reply sent and report marked as Resolved.", "success")
    return redirect(request.referrer or url_for('admin.view_commission_reports'))

@admin_bp.route('/commission-report/close/<int:report_id>')
def close_commission_report(report_id):
    report = CommissionReport.query.get_or_404(report_id)
    report.status = 'Closed'
    report.updated_at = datetime.utcnow()
    db.session.commit()
    
    log_audit("CLOSE_COMMISSION_REPORT", f"Closed commission report ID: {report_id}")
    flash("Commission report closed.", "success")
    return redirect(request.referrer or url_for('admin.view_commission_reports'))

# ==================== SELLER FEEDBACKS ====================

@admin_bp.route('/seller-feedbacks')
@login_required
def view_seller_feedbacks():
    if current_user.role not in ['admin', 'sub_admin']:
        flash("Unauthorized access.", "danger")
        return redirect(url_for('main.index'))
    feedbacks = SellerFeedback.query.order_by(SellerFeedback.is_read.asc(), SellerFeedback.created_at.desc()).all()
    return render_template('admin/seller_feedbacks.html', feedbacks=feedbacks)

@admin_bp.route('/seller-feedback/read/<int:feedback_id>')
@login_required
def mark_feedback_read(feedback_id):
    if current_user.role not in ['admin', 'sub_admin']:
        flash("Unauthorized access.", "danger")
        return redirect(url_for('main.index'))
    fb = SellerFeedback.query.get_or_404(feedback_id)
    fb.is_read = True
    db.session.commit()
    log_audit("MARK_FEEDBACK_DONE", f"Marked feedback ID {feedback_id} from store {fb.store.name} as completed")
    flash("Feedback marked as completed.", "success")
    return redirect(request.referrer or url_for('admin.view_seller_feedbacks'))

# ==================== REJECT COMMISSION PAYMENT ====================

@admin_bp.route('/commission/reject/<int:payment_id>', methods=['POST'])
def reject_commission_payment(payment_id):
    # Admins and sub-admins are both permitted to act on pending commission
    # verifications. (Enforced globally by check_admin_role above, but kept
    # explicit here since this action changes seller money state.)
    if current_user.role not in ['admin', 'sub_admin']:
        flash("Unauthorized access.", "danger")
        return redirect(request.referrer or url_for('admin.dashboard'))

    cp = CommissionPayment.query.get_or_404(payment_id)
    
    if cp.status == 'Rejected':
        flash("This commission payment has already been rejected.", "info")
        return redirect(request.referrer or url_for('admin.dashboard'))
    
    reason = request.form.get('rejection_reason', '').strip()
    
    if not reason:
        reason = "Your payment details are incorrect. Therefore, the commission payment has been cancelled by the verification team. If you face any issues, please submit a complaint with the appropriate proof. Thank you."
    
    was_already_paid = (cp.status == 'Paid')
    
    cp.status = 'Rejected'
    cp.rejected_reason = reason
    cp.rejected_at = datetime.utcnow()
    cp.rejected_by = current_user.id
    
    store = cp.store
    
    # Either way, the amount is no longer considered paid, so it goes back
    # onto the seller's outstanding balance and the store is put back into
    # a "Requested" state so the seller is prompted to resubmit payment.
    if was_already_paid:
        # This payment had already been marked Paid — rejecting it now means the seller
        # still owes this amount. Restore it as an outstanding due (does not touch the
        # sales baseline, since we don't know exactly which sales it covered).
        store.commission_carryover_amount = (store.commission_carryover_amount or 0.0) + cp.amount
    
    store.commission_payment_status = 'Requested'
    store.commission_requested_at = datetime.utcnow()
    
    db.session.commit()
    
    log_audit("REJECT_COMMISSION", f"Rejected commission payment ID: {payment_id} for {store.name}" + (" (previously marked Paid — amount restored as due)" if was_already_paid else ""))
    
    # Notify seller
    store_user = User.query.filter_by(id=store.user_id).first()
    if store_user:
        notify_user(store_user.id, "Commission Payment Rejected", 
                    reason, "alert")
    
    try:
        from app import emit_commission_update
        emit_commission_update(store.id, 'Rejected', cp.amount)
    except Exception:
        pass
    
    flash(f"Commission payment rejected for {store.name}.", "success")
    return redirect(request.referrer or url_for('admin.dashboard'))

# ==================== GLOBAL COMMISSION PERCENTAGE ====================

@admin_bp.route('/settings/commission-percentage', methods=['POST'])
def update_global_commission():
    if current_user.role != 'admin':
        flash("Only Main Admin can change global settings.", "danger")
        return redirect(request.referrer or url_for('admin.dashboard'))
    
    percentage = request.form.get('global_commission_percentage', type=float)
    if percentage is None or percentage < 0 or percentage > 100:
        flash("Invalid commission percentage (0-100).", "danger")
        return redirect(request.referrer or url_for('admin.system_settings'))
    
    # Save to SystemSettings
    setting = SystemSetting.query.filter_by(key='GLOBAL_COMMISSION_PERCENTAGE').first()
    if setting:
        setting.value = str(percentage)
    else:
        setting = SystemSetting(key='GLOBAL_COMMISSION_PERCENTAGE', value=str(percentage), group='general')
        db.session.add(setting)
    
    # Apply to all sellers immediately — lock in already-accrued dues at each seller's
    # OLD rate first, so the new percentage only ever applies to sales made from now on.
    stores = StoreProfile.query.all()
    for store in stores:
        store.lock_in_commission_rate_change(percentage)
    db.session.commit()
    
    log_audit("UPDATE_GLOBAL_COMMISSION", f"Updated global commission to {percentage}% for all sellers (existing accrued dues locked in at prior rates)")
    
    # Notify via Socket.IO
    try:
        from app import emit_settings_update
        emit_settings_update()
    except Exception:
        pass
    
    flash(f"Global commission updated to {percentage}% and applied to all sellers.", "success")
    return redirect(request.referrer or url_for('admin.system_settings'))

# ==================== GLOBAL USER SEARCH ====================

@admin_bp.route('/user/search')
def user_search():
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify([])
    
    results = []
    
    # Collect user IDs that match via phone number (Address) or store contact number
    phone_user_ids = [row[0] for row in db.session.query(Address.user_id).filter(Address.phone.ilike(f"%{q}%")).all()]
    phone_store_user_ids = [row[0] for row in db.session.query(StoreProfile.user_id).filter(StoreProfile.store_contact.ilike(f"%{q}%")).all()]
    matching_user_ids = list(set(phone_user_ids + phone_store_user_ids))
    
    # Search by User ID, Seller ID (store id), Name, Email, Phone, Store Name
    filters = [
        User.username.ilike(f"%{q}%"),
        User.email.ilike(f"%{q}%"),
    ]
    if q.isdigit():
        filters.append(User.id == int(q))
    if matching_user_ids:
        filters.append(User.id.in_(matching_user_ids))
    
    users = User.query.filter(db.or_(*filters)).limit(20).all()
    
    for user in users:
        result = {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'role': user.role,
            'is_active': user.is_active
        }
        if user.role == 'seller' and user.store_profile:
            result['store_name'] = user.store_profile.name
            result['store_id'] = user.store_profile.id
            # Check phone from store contact
            result['phone'] = user.store_profile.store_contact or ''
        else:
            result['store_name'] = ''
            result['store_id'] = ''
            # Get phone from addresses
            addr = Address.query.filter_by(user_id=user.id).first()
            result['phone'] = addr.phone if addr else ''
        
        results.append(result)
    
    # Also search stores by name or Seller ID (store id)
    store_filters = [StoreProfile.name.ilike(f"%{q}%")]
    if q.isdigit():
        store_filters.append(StoreProfile.id == int(q))
    stores = StoreProfile.query.filter(db.or_(*store_filters)).limit(10).all()
    for store in stores:
        if store.user_id not in [r['id'] for r in results]:
            results.append({
                'id': store.user_id,
                'username': store.user.username if store.user else '',
                'email': store.user.email if store.user else '',
                'role': 'seller',
                'is_active': store.user.is_active if store.user else False,
                'store_name': store.name,
                'store_id': store.id,
                'phone': store.store_contact or ''
            })
    
    return jsonify(results)

# ==================== SELLER APPROVAL WORKFLOWS ====================
@admin_bp.route('/seller/approve/<int:store_id>')
def approve_seller(store_id):
    store = StoreProfile.query.get_or_404(store_id)
    store.status = 'Approved'
    db.session.commit()
    log_audit("APPROVE_SELLER_STORE", f"Approved store '{store.name}' (User ID: {store.user_id})")
    
    # Notify seller
    store_user = User.query.filter_by(id=store.user_id).first()
    if store_user:
        notify_user(store_user.id, "Store Approved", 
                    f"Congratulations! Your store '{store.name}' has been approved by the admin.", "general")
    
    flash(f"Seller account and store '{store.name}' have been approved successfully.", "success")
    return redirect(request.referrer or url_for('admin.dashboard'))

@admin_bp.route('/seller/reject/<int:store_id>')
def reject_seller(store_id):
    store = StoreProfile.query.get_or_404(store_id)
    store.status = 'Rejected'
    db.session.commit()
    log_audit("REJECT_SELLER_STORE", f"Rejected store '{store.name}' (User ID: {store.user_id})")
    
    # Notify seller
    store_user = User.query.filter_by(id=store.user_id).first()
    if store_user:
        notify_user(store_user.id, "Store Rejected", 
                    f"Your store '{store.name}' application has been rejected. Please contact support.", "alert")
    
    flash(f"Seller application for '{store.name}' has been rejected.", "warning")
    return redirect(request.referrer or url_for('admin.dashboard'))

@admin_bp.route('/seller/export-pdf/<int:store_id>')
@login_required
def export_seller_pdf(store_id):
    if not is_admin_or_sub_admin():
        flash("Unauthorized access. Admins only.", "danger")
        return redirect(url_for('main.index'))
        
    store = StoreProfile.query.get_or_404(store_id)
    
    from services.seller_pdf import SellerPdfService
    pdf_buffer = SellerPdfService.generate_seller_profile_pdf(store)
    
    # Clean filename
    clean_name = "".join(c for c in store.name if c.isalnum() or c in (' ', '_', '-')).strip().replace(' ', '_')
    filename = f"Seller_Verification_{clean_name}_{store.id}.pdf"
    
    return send_file(
        pdf_buffer,
        as_attachment=True,
        download_name=filename,
        mimetype="application/pdf"
    )

# ----------------- USER MANAGE -----------------
@admin_bp.route('/users')
def manage_users():
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin/users.html', users=users, is_main_admin=current_user.role == 'admin')

@admin_bp.route('/user/toggle/<int:user_id>')
def toggle_user_active(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("You cannot disable your own admin account.", "danger")
        return redirect(request.referrer or url_for('admin.manage_users'))
        
    user.is_active = not user.is_active
    
    # Permanently remove UPI details when seller is disabled
    if not user.is_active and user.role == 'seller' and user.store_profile:
        user.store_profile.upi_id = None
        user.store_profile.qr_code_path = None
        
    db.session.commit()
    log_audit("TOGGLE_USER_STATUS", f"Toggled user {user.username} active status to {user.is_active}")
    
    # Notify user
    notify_user(user.id, "Account Status Changed", 
                f"Your account status has been updated to {'active' if user.is_active else 'disabled'}.", "alert")
    
    flash(f"User '{user.username}' status updated.", "success")
    return redirect(request.referrer or url_for('admin.manage_users'))

# ----------------- CATEGORY & BRAND MANAGE -----------------
@admin_bp.route('/category/add', methods=['POST'])
def add_category():
    name = request.form.get('name', '').strip()
    parent_id = request.form.get('parent_id', type=int)
    icon = request.form.get('icon', 'fa-tag')
    
    if not name:
        flash("Category name is required.", "danger")
        return redirect(url_for('admin.dashboard') + '#catalog')
        
    from werkzeug.utils import secure_filename
    slug = secure_filename(name).lower()
    
    # Check duplicate slug
    existing = Category.query.filter_by(slug=slug).first()
    if existing:
        slug = f"{slug}-{uuid.uuid4().hex[:4]}"
        
    cat = Category(name=name, slug=slug, parent_id=parent_id or None, icon=icon)
    db.session.add(cat)
    db.session.commit()
    
    # Handle category icon image upload
    icon_file = request.files.get('icon_image')
    if icon_file and icon_file.filename:
        from services.storage import upload_file_field
        key, err = upload_file_field(icon_file, 'categories')
        if err:
            flash(f"Failed to upload category icon: {err}", "danger")
        elif key:
            cat.icon = key
            db.session.commit()
        
    try:
        from app import clear_categories_cache
        clear_categories_cache()
    except Exception:
        pass
    log_audit("ADD_CATEGORY", f"Created category '{name}'")
    flash(f"Category '{name}' created successfully.", "success")
    return redirect(url_for('admin.dashboard') + '#catalog')

@admin_bp.route('/brand/add', methods=['POST'])
def add_brand():
    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()
    category_id = request.form.get('category_id', type=int)
    
    if not name:
        flash("Brand name is required.", "danger")
        return redirect(url_for('admin.dashboard') + '#catalog')
        
    from werkzeug.utils import secure_filename
    slug = secure_filename(name).lower()
    
    brand = Brand(name=name, slug=slug, description=description, category_id=category_id or None)
    db.session.add(brand)
    db.session.commit()
    log_audit("ADD_BRAND", f"Created brand '{name}' linked to category ID {category_id}")
    flash(f"Brand '{name}' created successfully.", "success")
    return redirect(url_for('admin.dashboard') + '#catalog')

@admin_bp.route('/category/delete/<int:cat_id>')
@login_required
def delete_category(cat_id):
    if current_user.role not in ['admin', 'sub_admin']:
        flash("Unauthorized access.", "danger")
        return redirect(url_for('main.index'))
    cat = Category.query.get_or_404(cat_id)
    name = cat.name
    
    if cat.icon:
        from services.storage import storage_service
        storage_service.delete_file(cat.icon)
        
    db.session.delete(cat)
    db.session.commit()
    
    try:
        from app import clear_categories_cache
        clear_categories_cache()
    except Exception:
        pass
        
    log_audit("DELETE_CATEGORY", f"Deleted category '{name}'")
    flash(f"Category '{name}' deleted successfully.", "success")
    return redirect(url_for('admin.dashboard') + '#catalog')

@admin_bp.route('/brand/delete/<int:brand_id>')
@login_required
def delete_brand(brand_id):
    if current_user.role not in ['admin', 'sub_admin']:
        flash("Unauthorized access.", "danger")
        return redirect(url_for('main.index'))
    brand = Brand.query.get_or_404(brand_id)
    name = brand.name
    
    db.session.delete(brand)
    db.session.commit()
    
    log_audit("DELETE_BRAND", f"Deleted brand '{name}'")
    flash(f"Brand '{name}' deleted successfully.", "success")
    return redirect(url_for('admin.dashboard') + '#catalog')

# ----------------- CAROUSEL BANNERS -----------------
@admin_bp.route('/banner/add', methods=['POST'])
def add_banner():
    title = request.form.get('title', '').strip()
    subtitle = request.form.get('subtitle', '').strip()
    link_url = request.form.get('link_url', '').strip()
    order_seq = request.form.get('order_seq', 0, type=int)
    
    expires_at_str = request.form.get('expires_at')
    expires_at = None
    if expires_at_str:
        try:
            expires_at = datetime.fromisoformat(expires_at_str)
        except ValueError:
            pass
            
    banner_file = request.files.get('banner_image')
    if not banner_file or not banner_file.filename:
        flash("Banner image is required.", "danger")
        return redirect(url_for('admin.dashboard') + '#banners')
        
    from services.storage import upload_file_field
    key, err = upload_file_field(banner_file, 'banners')
    if err or not key:
        flash(f"Failed to upload banner image: {err or 'Unknown error'}", "danger")
        return redirect(url_for('admin.dashboard') + '#banners')
        
    banner = Banner(
        title=title, subtitle=subtitle, image_path=key,
        link_url=link_url, order_seq=order_seq, is_active=True,
        expires_at=expires_at
    )
    db.session.add(banner)
    db.session.commit()
    log_audit("ADD_BANNER", f"Added banner: {title}")
    flash("Banner uploaded.", "success")
    return redirect(url_for('admin.dashboard') + '#banners')

@admin_bp.route('/banner/delete/<int:banner_id>')
def delete_banner(banner_id):
    banner = Banner.query.get_or_404(banner_id)
    if banner.image_path:
        from services.storage import storage_service
        storage_service.delete_file(banner.image_path)
    db.session.delete(banner)
    db.session.commit()
    log_audit("DELETE_BANNER", f"Deleted banner: {banner.title}")
    flash("Banner deleted successfully.", "success")
    return redirect(url_for('admin.dashboard') + '#banners')

# ----------------- RETURNS & AUTOMATIC REFUNDS -----------------
@admin_bp.route('/return/process/<int:ret_id>/<action>')
def process_return(ret_id, action):
    ret = ReturnRequest.query.get_or_404(ret_id)
    order_item = OrderItem.query.get(ret.order_item_id)
    order = Order.query.get(order_item.order_id)
    
    if action == 'approve':
        ret.status = 'Approved'
        # Refund payment automatically to user's wallet
        refund_amount = order_item.total_price
        
        # Deduct earnings from seller profile
        seller = StoreProfile.query.get(order_item.product.seller_id)
        if seller:
            seller.balance = max(seller.balance - refund_amount, 0.0)
            
        # Add to customer wallet balance
        wallet_tx = WalletTransaction(
            user_id=order.user_id,
            amount=refund_amount,
            type='credit',
            description=f"Refund for returned item: {order_item.product_name}"
        )
        db.session.add(wallet_tx)
        
        # Create Refund history record
        ref = Refund(
            return_request_id=ret.id,
            order_id=order.id,
            amount=refund_amount,
            status='Completed',
            transaction_id=f"REF-{uuid.uuid4().hex[:12].upper()}"
        )
        db.session.add(ref)
        
        db.session.commit()
        log_audit("APPROVE_RETURN", f"Approved return and refunded INR {refund_amount} to user ID: {order.user_id}")
        
        # Notify customer
        notify_user(order.user_id, "Return Approved", 
                    f"Your return for '{order_item.product_name}' has been approved. INR {refund_amount:.2f} has been refunded to your wallet.", "general")
        
        flash(f"Return approved and INR {refund_amount:.2f} refunded to wallet.", "success")
        
    elif action == 'reject':
        ret.status = 'Rejected'
        db.session.commit()
        log_audit("REJECT_RETURN", f"Rejected return request ID: {ret_id}")
        
        # Notify customer
        notify_user(order.user_id, "Return Rejected", 
                    f"Your return for '{order_item.product_name}' has been rejected.", "alert")
        
        flash("Return request rejected.", "info")
        
    return redirect(request.referrer or url_for('admin.dashboard'))

def cleanup_expired_banners():
    now = datetime.utcnow()
    expired_banners = Banner.query.filter(Banner.expires_at != None, Banner.expires_at <= now).all()
    from services.storage import storage_service
    for banner in expired_banners:
        if banner.image_path:
            storage_service.delete_file(banner.image_path)
        db.session.delete(banner)
    if expired_banners:
        db.session.commit()

# ----------------- SYSTEM SETTINGS -----------------
@admin_bp.route('/settings', methods=['GET', 'POST'])
def system_settings():
    # Sub Admin cannot access Global Settings
    if current_user.role == 'sub_admin':
        flash("Sub Admins are not allowed to modify Global Settings.", "danger")
        return redirect(request.referrer or url_for('admin.dashboard'))
    
    from config import Config
    from werkzeug.utils import secure_filename
    
    if request.method == 'POST':
        # Handle regular form fields
        for key, val in request.form.items():
            if key == 'csrf_token':
                continue
            setting = SystemSetting.query.filter_by(key=key).first()
            if setting:
                setting.value = val
            else:
                setting = SystemSetting(key=key, value=val)
                db.session.add(setting)
                
        # Handle checkboxes (payment and delivery status)
        for key in ['ENABLE_UPI', 'ENABLE_COD', 'ENABLE_OUT_FOR_DELIVERY', 'ENABLE_DELIVERED']:
            val = 'true' if request.form.get(key) else 'false'
            setting = SystemSetting.query.filter_by(key=key).first()
            if setting:
                setting.value = val
            else:
                setting = SystemSetting(key=key, value=val)
                db.session.add(setting)

        # Handle Return System setting
        val = 'true' if request.form.get('ENABLE_RETURNS') else 'false'
        setting = SystemSetting.query.filter_by(key='ENABLE_RETURNS').first()
        if setting:
            setting.value = val
        else:
            setting = SystemSetting(key='ENABLE_RETURNS', value=val, group='general')
            db.session.add(setting)

        # Handle Admin QR Code Upload
        qr_file = request.files.get('ADMIN_QR_CODE')
        if qr_file and qr_file.filename:
            from services.storage import upload_file_field, storage_service
            setting = SystemSetting.query.filter_by(key='ADMIN_QR_CODE').first()
            old_qr = setting.value if setting else None
            
            key, err = upload_file_field(qr_file, 'admin/qr')
            if err:
                flash(f"Failed to upload admin QR code: {err}", "danger")
            elif key:
                if setting:
                    setting.value = key
                else:
                    setting = SystemSetting(key='ADMIN_QR_CODE', value=key)
                    db.session.add(setting)
                if old_qr and old_qr != key:
                    storage_service.delete_file(old_qr)

        db.session.commit()
        log_audit("UPDATE_SETTINGS", "System settings updated")
        
        # Notify via Socket.IO
        try:
            from app import emit_settings_update
            emit_settings_update()
        except Exception:
            pass
        
        flash("Settings saved successfully.", "success")
        return redirect(request.referrer or url_for('admin.system_settings'))
        
    settings = SystemSetting.query.all()
    s_dict = {s.key: s.value for s in settings}
    return render_template('admin/settings.html', settings=s_dict)

# ----------------- LOGS BROWSER -----------------
@admin_bp.route('/logs')
def view_logs():
    audit_logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(100).all()
    return render_template('admin/logs.html', logs=audit_logs)

# ----------------- BACKUP & RESTORE -----------------
@admin_bp.route('/backup/create')
def create_backup():
    success, msg = BackupService.backup_database()
    if success:
        log_audit("DATABASE_BACKUP", f"Database backed up: {msg}")
        flash(f"Backup created successfully: {msg}", "success")
    else:
        flash(f"Backup failed: {msg}", "danger")
    return redirect(url_for('admin.dashboard') + '#backups')

@admin_bp.route('/backup/restore', methods=['POST'])
def restore_backup():
    filename = request.form.get('filename')
    if not filename:
        flash("No backup file selected.", "danger")
        return redirect(url_for('admin.dashboard') + '#backups')
        
    success, msg = BackupService.restore_database(filename)
    if success:
        log_audit("DATABASE_RESTORE", f"Database restored from: {filename}")
        flash("Database restored successfully.", "success")
    else:
        flash(f"Restore failed: {msg}", "danger")
    return redirect(url_for('admin.dashboard') + '#backups')

# ----------------- SUPPORT TICKET PANEL -----------------
@admin_bp.route('/ticket/<int:ticket_id>', methods=['GET', 'POST'])
def view_ticket(ticket_id):
    ticket = SupportTicket.query.get_or_404(ticket_id)
    if request.method == 'POST':
        message = request.form.get('message', '').strip()
        if message:
            msg = SupportMessage(ticket_id=ticket.id, user_id=current_user.id, message=message, is_admin=True)
            ticket.status = "In Progress"
            db.session.add(msg)
            db.session.commit()
            
            # Notify customer
            notify_user(ticket.user_id, f"Support Ticket #{ticket.id} Update", 
                        f"A support agent has replied to your ticket: {message}", "general")
            
            from services.email_service import EmailService
            EmailService.send_mock_support_email(
                ticket.user.email,
                f"Update on Support Ticket #{ticket.id}: {ticket.subject}",
                f"A support agent has replied to your ticket:\n\n{message}"
            )
            
            flash("Reply added.", "success")
            return redirect(request.referrer or url_for('admin.view_ticket', ticket_id=ticket.id))
            
    return render_template('admin/ticket_detail.html', ticket=ticket)

@admin_bp.route('/ticket/close/<int:ticket_id>')
def close_ticket(ticket_id):
    ticket = SupportTicket.query.get_or_404(ticket_id)
    ticket.status = "Closed"
    db.session.commit()
    log_audit("CLOSE_TICKET", f"Closed support ticket ID: {ticket_id}")
    
    # Notify customer
    notify_user(ticket.user_id, f"Support Ticket #{ticket.id} Closed", 
                f"Your support ticket '{ticket.subject}' has been closed.", "general")
    
    flash("Ticket marked as Closed.", "success")
    return redirect(request.referrer or url_for('admin.dashboard'))

@admin_bp.route('/seller/commission/<int:store_id>', methods=['POST'])
def change_commission(store_id):
    store = StoreProfile.query.get_or_404(store_id)
    commission = request.form.get('commission_percentage', type=float)
    if commission is not None and 0 <= commission <= 100:
        old_percentage = store.commission_percentage
        store.lock_in_commission_rate_change(commission)
        db.session.commit()
        log_audit("CHANGE_COMMISSION", f"Updated commission for {store.name} from {old_percentage}% to {commission}% (existing accrued dues locked in at old rate)")
        flash(f"Commission for {store.name} updated to {commission}%. Already-accrued dues remain locked in at the previous rate; only new sales will use the new rate.", "success")
    else:
        flash("Invalid commission percentage.", "danger")
    return redirect(url_for('admin.dashboard') + '#commissions')

@admin_bp.route('/seller/commission-request/<int:store_id>')
def request_commission(store_id):
    store = StoreProfile.query.get_or_404(store_id)
    due = store.commission_due
    if due <= 0:
        flash(f"No pending commission due for {store.name}.", "info")
        return redirect(url_for('admin.dashboard') + '#commissions')
        
    store.commission_payment_status = 'Requested'
    store.commission_requested_at = datetime.utcnow()
    db.session.commit()
    
    log_audit("REQUEST_COMMISSION", f"Admin requested commission payment of INR {due} from {store.name}")
    
    # Notify seller
    store_user = User.query.filter_by(id=store.user_id).first()
    if store_user:
        notify_user(store_user.id, "Commission Payment Requested", 
                    f"Admin has requested a commission payment of INR {due:.2f}. Please pay within 3 days.", "alert")
    
    flash(f"Commission payment request sent to {store.name}.", "success")
    return redirect(url_for('admin.dashboard') + '#commissions')

@admin_bp.route('/commission/approve/<int:payment_id>')
def approve_commission_payment(payment_id):
    cp = CommissionPayment.query.get_or_404(payment_id)
    cp.status = 'Paid'
    
    store = cp.store
    store.sales_at_last_commission = store.total_sales
    store.commission_carryover_amount = 0.0
    store.commission_payment_status = 'Paid'
    store.commission_requested_at = None
    
    if store.status == 'Suspended':
        store.status = 'Approved'
        
    db.session.commit()
    log_audit("APPROVE_COMMISSION", f"Approved commission payment of INR {cp.amount} from {store.name}")
    
    # Notify seller
    store_user = User.query.filter_by(id=store.user_id).first()
    if store_user:
        notify_user(store_user.id, "Commission Payment Approved", 
                    f"Your commission payment of INR {cp.amount:.2f} has been approved.", "general")
    
    try:
        from app import emit_commission_update
        emit_commission_update(store.id, 'Paid', cp.amount)
    except Exception:
        pass
    
    flash(f"Commission payment approved for {store.name}.", "success")
    return redirect(url_for('admin.dashboard') + '#commissions')

@admin_bp.route('/notice/add', methods=['POST'])
def add_notice():
    target = request.form.get('target')
    message = request.form.get('message', '').strip()
    
    if not message:
        flash("Notice message cannot be empty.", "danger")
        return redirect(url_for('admin.dashboard') + '#notices')
        
    from models import SellerNotice
    store_id = None if target == 'all' else int(target)
    
    notice = SellerNotice(store_id=store_id, message=message)
    db.session.add(notice)
    db.session.commit()
    
    # Notify affected sellers
    if store_id:
        store = StoreProfile.query.get(store_id)
        if store:
            notify_user(store.user_id, "New Notice", message, "general")
    else:
        # Notify all sellers
        all_sellers = User.query.filter_by(role='seller').all()
        for s in all_sellers:
            notify_user(s.id, "New Admin Notice", message, "general")
    
    flash("Administrative notice published successfully.", "success")
    return redirect(url_for('admin.dashboard') + '#notices')

@admin_bp.route('/notice/delete/<int:notice_id>')
@login_required
def delete_notice(notice_id):
    if current_user.role not in ['admin', 'sub_admin']:
        flash("Unauthorized access.", "danger")
        return redirect(url_for('main.index'))
        
    notice = SellerNotice.query.get_or_404(notice_id)
    target_str = f"Store: {notice.store.name}" if notice.store_id else "Global (All)"
    msg_preview = notice.message[:30] + "..." if len(notice.message) > 30 else notice.message
    
    db.session.delete(notice)
    db.session.commit()
    
    log_audit("DELETE_NOTICE", f"Deleted notice to {target_str}: '{msg_preview}'")
    flash("Notice deleted successfully.", "success")
    return redirect(url_for('admin.dashboard') + '#notices')

@admin_bp.route('/complaint/warn/<int:complaint_id>', methods=['POST'])
def warn_seller_for_complaint(complaint_id):
    complaint = Complaint.query.get_or_404(complaint_id)
    warning_message = request.form.get('warning_message', '').strip()
    
    if not warning_message:
        flash("Warning message cannot be empty.", "danger")
        return redirect(url_for('admin.dashboard') + '#complaints')
        
    first_item = complaint.order.items[0]
    store_id = first_item.product.seller_id
    
    notice = SellerNotice(
        store_id=store_id, 
        message=f"WARNING FROM ADMIN regarding Order #{complaint.order.order_number}: {warning_message}"
    )
    db.session.add(notice)
    
    complaint.status = 'Resolved'
    db.session.commit()
    
    # Notify seller
    store = StoreProfile.query.get(store_id)
    if store:
        notify_user(store.user_id, "Warning from Admin", 
                    f"Warning regarding Order #{complaint.order.order_number}: {warning_message}", "alert")
    
    flash("Warning sent to seller and complaint marked as resolved.", "success")
    return redirect(url_for('admin.dashboard') + '#complaints')