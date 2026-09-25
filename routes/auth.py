from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta
from database import db
from models import User, Role, StoreProfile, AuditLog

auth_bp = Blueprint('auth', __name__)

def log_audit(user, action, details=None):
    try:
        ip = request.remote_addr
        ua = request.headers.get('User-Agent', '')[:250] if request.headers.get('User-Agent') else ''
        log = AuditLog(
            user_id=user.id if user else None,
            role=user.role if user else None,
            action=action,
            ip_address=ip,
            user_agent=ua,
            details=details
        )
        db.session.add(log)
        db.session.commit()
    except Exception:
        db.session.rollback()

import logging
logger = logging.getLogger('auth')

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
        
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        role = request.form.get('role', 'customer')
        
        logger.info(f"[REGISTRATION ATTEMPT] Username: '{username}', Email: '{email}', Role: '{role}'")

        try:
            if not username or not email or not password:
                flash('All fields are required.', 'danger')
                return render_template('auth/register.html'), 400
                
            if password != confirm_password:
                flash('Passwords do not match.', 'danger')
                return render_template('auth/register.html'), 400
                
            if len(password) < 6:
                flash('Password must be at least 6 characters long.', 'danger')
                return render_template('auth/register.html'), 400
                
            # Check if user exists
            if User.query.filter((User.username == username) | (User.email == email)).first():
                flash('Username or Email already registered.', 'danger')
                return render_template('auth/register.html'), 400
                
            # If Seller, validate documents
            uploaded_keys = []
            seller_docs = {}
            if role == Role.SELLER:
                aadhaar_number = request.form.get('aadhaar_number', '').strip()
                agreed = True if request.form.get('agreed') else False
                
                aadhaar_front_file = request.files.get('aadhaar_front')
                aadhaar_back_file = request.files.get('aadhaar_back')
                photo_file = request.files.get('photo')
                sig_file = request.files.get('signature')
                
                if not aadhaar_number or not agreed or \
                   not aadhaar_front_file or not aadhaar_front_file.filename or \
                   not aadhaar_back_file or not aadhaar_back_file.filename or \
                   not photo_file or not photo_file.filename or \
                   not sig_file or not sig_file.filename:
                    flash('All seller verification documents and the legal agreement are required.', 'danger')
                    return render_template('auth/register.html'), 400
                
                # Check Aadhaar duplicate/banned status
                existing_seller_with_aadhaar = StoreProfile.query.filter_by(aadhaar_number=aadhaar_number).first()
                if existing_seller_with_aadhaar:
                    seller_user = User.query.get(existing_seller_with_aadhaar.user_id)
                    if seller_user and (not seller_user.is_active or seller_user.is_suspended or existing_seller_with_aadhaar.status in ['Suspended', 'Rejected']):
                        flash('Seller details are banned.', 'danger')
                        return render_template('auth/register.html'), 400
                
                from services.storage import upload_file_field, storage_service
                doc_category = f"seller-documents/{username}"
                
                file_map = [
                    ('aadhaar_front', aadhaar_front_file),
                    ('aadhaar_back', aadhaar_back_file),
                    ('photo', photo_file),
                    ('signature', sig_file)
                ]
                
                for field_name, file_obj in file_map:
                    logger.info(f"[SELLER REG UPLOAD START] Username: {username}, Field: {field_name}, Original File: {file_obj.filename}")
                    key, err = upload_file_field(file_obj, doc_category, is_private=True)
                    if err or not key:
                        logger.error(f"[SELLER REG UPLOAD FAIL] Username: {username}, Field: {field_name}, Error: {err}")
                        # Cleanup all previously uploaded R2 keys
                        for uploaded_k in uploaded_keys:
                            try:
                                storage_service.delete_file(uploaded_k)
                            except Exception:
                                pass
                        flash(f"Seller document upload failed ({field_name}): {err or 'Unknown upload error'}", 'danger')
                        return render_template('auth/register.html'), 400
                    
                    uploaded_keys.append(key)
                    seller_docs[field_name] = key
                    logger.info(f"[SELLER REG UPLOAD SUCCESS] Username: {username}, Field: {field_name} -> Object Key: {key}")
                
                seller_docs['aadhaar_number'] = aadhaar_number
                seller_docs['agreed_to_terms'] = True

            # Atomic Database Transaction: Create User + Store Profile together
            new_user = User(username=username, email=email, role=role, is_active=True)
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.flush()  # Obtains generated new_user.id
            
            if role == Role.SELLER:
                store = StoreProfile(
                    user_id=new_user.id,
                    name=f"{username}'s Store",
                    description="Welcome to my new e-commerce store!",
                    balance=0.0,
                    status='Pending',
                    **seller_docs
                )
                db.session.add(store)
                
            if role == Role.CUSTOMER:
                door_no = request.form.get('door_no', '').strip()
                if door_no:
                    from models import Address
                    addr = Address(
                        user_id=new_user.id,
                        title="Default Home",
                        fullName=username,
                        addressLine1=f"{door_no}, {request.form.get('street', '')}",
                        addressLine2=request.form.get('landmark', ''),
                        city=request.form.get('village_city', ''),
                        state=request.form.get('state', ''),
                        postalCode=request.form.get('pin_code', ''),
                        country=request.form.get('country', 'India'),
                        phone=request.form.get('contact_number', ''),
                        is_default=True,
                        door_no=door_no,
                        street=request.form.get('street', ''),
                        village_city=request.form.get('village_city', ''),
                        post_name=request.form.get('post_name', ''),
                        taluk_name=request.form.get('taluk_name', ''),
                        district=request.form.get('district', ''),
                        landmark=request.form.get('landmark', ''),
                        contact_number=request.form.get('contact_number', '')
                    )
                    db.session.add(addr)

            db.session.commit()
            log_audit(new_user, "REGISTER", f"Registered as role: {role}")
            logger.info(f"[REGISTRATION COMPLETE] User ID: {new_user.id}, Username: {username}, Role: {role}")
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('auth.login'))

        except Exception as ex:
            db.session.rollback()
            if 'uploaded_keys' in locals():
                from services.storage import storage_service
                for uploaded_k in uploaded_keys:
                    try:
                        storage_service.delete_file(uploaded_k)
                    except Exception:
                        pass
            logger.exception(f"[REGISTRATION CRASH] Error during registration for '{username}': {ex}")
            flash('Registration failed due to a server error. Please try again.', 'danger')
            return render_template('auth/register.html'), 500

    return render_template('auth/register.html')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
        
    if request.method == 'POST':
        login_input = request.form.get('login_input', '').strip() # Can be email or username
        password = request.form.get('password', '')
        remember = True if request.form.get('remember') else False
        
        user = User.query.filter((User.email == login_input) | (User.username == login_input)).first()
        
        if not user:
            flash('Invalid login credentials.', 'danger')
            return render_template('auth/login.html')
            
        # Lockout check
        if user.is_locked:
            flash(f"Account locked due to multiple failed attempts. Try again after {user.locked_until.strftime('%H:%M:%S UTC')}.", 'danger')
            return render_template('auth/login.html')
            
        if not user.is_active:
            flash('This account is disabled.', 'danger')
            return render_template('auth/login.html')
            
        if user.check_password(password):
            # Check Seller status
            if user.role == Role.SELLER:
                store = user.store_profile
                if not store or store.status != 'Approved':
                    flash("Your seller account is pending approval by the Admin. You cannot login yet.", "warning")
                    return render_template('auth/login.html')
            
            # Check Verifier status
            if user.role == 'verifier':
                if user.is_suspended:
                    flash("Your verifier account is suspended by the seller.", "danger")
                    return render_template('auth/login.html')
            
            # Check Sub Admin status
            if user.role == 'sub_admin':
                if not user.is_active:
                    flash("Your Sub Admin account has been blocked by the Main Admin.", "danger")
                    return render_template('auth/login.html')
            
            # Transparently upgrade legacy bcrypt hashes to ultra-fast format
            if user.password_hash and (user.password_hash.startswith('$2b$') or user.password_hash.startswith('$2a$')):
                user.set_password(password)
                
            # Reset failed attempts
            user.failed_login_attempts = 0
            user.locked_until = None
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
            
            login_user(user, remember=remember)
            log_audit(user, "LOGIN", "Login successful")
            
            # Redirect by role
            if user.role == Role.ADMIN:
                return redirect(url_for('admin.dashboard'))
            elif user.role == 'sub_admin':
                return redirect(url_for('admin.dashboard'))
            elif user.role == Role.SELLER:
                return redirect(url_for('seller.dashboard'))
            elif user.role == 'verifier':
                return redirect(url_for('seller.verifier_dashboard'))
            else:
                return redirect(url_for('main.index'))
        else:
            # Increment failed attempts
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= 5:
                user.locked_until = datetime.utcnow() + timedelta(minutes=10)
                log_audit(user, "LOCKOUT", "Account locked for 10 minutes due to 5 failures")
                flash('Too many failed attempts. Account locked for 10 minutes.', 'danger')
            else:
                db.session.commit()
                log_audit(user, "LOGIN_FAILED", f"Failed attempt #{user.failed_login_attempts}")
                flash(f'Invalid credentials. {5 - user.failed_login_attempts} attempts remaining.', 'danger')
                
            return render_template('auth/login.html')
            
    return render_template('auth/login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    log_audit(current_user, "LOGOUT", "Logout successful")
    logout_user()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('main.index'))

@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        user = User.query.filter_by(email=email).first()
        
        if user:
            log_audit(user, "FORGOT_PASSWORD_REQUEST", "Password reset link requested")
            # In production, send email. Here we just display a mock reset link.
            reset_url = url_for('auth.reset_password', email=email, token="MOCK_TOKEN_12345", _external=True)
            flash(f"Demo Reset Link: <a href='{reset_url}'>Click here to reset your password</a>", 'info')
        else:
            flash('Email not found.', 'danger')
            
    return render_template('auth/forgot_password.html')

@auth_bp.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    email = request.args.get('email', '')
    token = request.args.get('token', '')
    
    if not email or not token:
        flash('Invalid reset link.', 'danger')
        return redirect(url_for('auth.login'))
        
    if request.method == 'POST':
        new_password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        if len(new_password) < 6:
            flash('Password must be at least 6 characters.', 'danger')
            return render_template('auth/reset_password.html')
            
        if new_password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('auth/reset_password.html')
            
        user = User.query.filter_by(email=email).first()
        if user:
            user.set_password(new_password)
            user.failed_login_attempts = 0
            user.locked_until = None
            db.session.commit()
            log_audit(user, "RESET_PASSWORD", "Password reset completed")
            flash('Password reset successful! Please login.', 'success')
            return redirect(url_for('auth.login'))
        else:
            flash('User not found.', 'danger')
            
    return render_template('auth/reset_password.html')