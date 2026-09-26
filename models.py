from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from database import db
import json
import bcrypt

# Association Table for User Permissions
user_permissions = db.Table('user_permissions',
    db.Column('user_id', db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
    db.Column('permission_id', db.Integer, db.ForeignKey('permissions.id', ondelete='CASCADE'), primary_key=True)
)

class Role:
    ADMIN = 'admin'
    SELLER = 'seller'
    CUSTOMER = 'customer'
    SUB_ADMIN = 'sub_admin'

class User(db.Model, UserMixin):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default=Role.CUSTOMER, index=True)
    
    # Account status & lockouts
    failed_login_attempts = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    email_verified = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Verifier fields
    seller_id = db.Column(db.Integer, db.ForeignKey('store_profiles.id', ondelete='SET NULL', use_alter=True, name='fk_users_seller_id'), nullable=True)
    is_suspended = db.Column(db.Boolean, default=False)
    
    # Relationships
    permissions = db.relationship('Permission', secondary=user_permissions, backref=db.backref('users', lazy='dynamic'))
    store_profile = db.relationship('StoreProfile', uselist=False, back_populates='user', cascade='all, delete-orphan', foreign_keys='StoreProfile.user_id')
    addresses = db.relationship('Address', back_populates='user', cascade='all, delete-orphan')
    orders = db.relationship('Order', back_populates='user', cascade='all, delete-orphan')
    cart_items = db.relationship('CartItem', back_populates='user', cascade='all, delete-orphan')
    wishlist = db.relationship('Wishlist', back_populates='user', cascade='all, delete-orphan')
    reviews = db.relationship('Review', back_populates='user', cascade='all, delete-orphan')
    wallet_transactions = db.relationship('WalletTransaction', back_populates='user', cascade='all, delete-orphan')
    reward_points = db.relationship('RewardPoint', back_populates='user', cascade='all, delete-orphan')
    support_tickets = db.relationship('SupportTicket', back_populates='user', cascade='all, delete-orphan')
    recently_viewed = db.relationship('RecentlyViewed', back_populates='user', cascade='all, delete-orphan')
    search_history = db.relationship('SearchHistory', back_populates='user', cascade='all, delete-orphan')
    notifications = db.relationship('Notification', back_populates='user', cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        if not self.password_hash:
            return False
        if self.password_hash.startswith('$2b$') or self.password_hash.startswith('$2a$'):
            try:
                return bcrypt.checkpw(password.encode('utf-8'), self.password_hash.encode('utf-8'))
            except Exception:
                return False
        return check_password_hash(self.password_hash, password)

    @property
    def is_locked(self):
        if self.locked_until and self.locked_until > datetime.utcnow():
            return True
        return False

    @property
    def wallet_balance(self):
        credits = sum(t.amount for t in self.wallet_transactions if t.type == 'credit')
        debits = sum(t.amount for t in self.wallet_transactions if t.type == 'debit')
        return credits - debits

    @property
    def reward_points_balance(self):
        credits = sum(p.points for p in self.reward_points if p.type == 'credit')
        debits = sum(p.points for p in self.reward_points if p.type == 'debit')
        return credits - debits

class Permission(db.Model):
    __tablename__ = 'permissions'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)

class StoreProfile(db.Model):
    __tablename__ = 'store_profiles'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    logo = db.Column(db.String(255), nullable=True)
    banner = db.Column(db.String(255), nullable=True)
    rating = db.Column(db.Float, default=5.0)
    balance = db.Column(db.Float, default=0.0)
    tax_number = db.Column(db.String(50), nullable=True)
    status = db.Column(db.String(30), default='Pending', index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # UPI / Scan & Pay fields
    upi_id = db.Column(db.String(120), nullable=True)
    qr_code_path = db.Column(db.String(255), nullable=True)
    
    # Onboarding Verification fields
    aadhaar_number = db.Column(db.String(20), nullable=True)
    aadhaar_front = db.Column(db.String(255), nullable=True)
    aadhaar_back = db.Column(db.String(255), nullable=True)
    photo = db.Column(db.String(255), nullable=True)
    signature = db.Column(db.String(255), nullable=True)
    agreed_to_terms = db.Column(db.Boolean, default=False)
    store_address = db.Column(db.String(255), nullable=True)
    store_contact = db.Column(db.String(100), nullable=True)
    
    # Commission fields
    commission_percentage = db.Column(db.Float, default=10.0)
    total_sales = db.Column(db.Float, default=0.0)
    sales_at_last_commission = db.Column(db.Float, default=0.0)
    commission_payment_status = db.Column(db.String(30), default='Paid') # 'Paid', 'Requested', 'Submitted', 'Suspended'
    commission_requested_at = db.Column(db.DateTime, nullable=True)
    # Amount locked in at a PRIOR commission percentage before a rate change. When the
    # global/individual commission % is changed, any sales already accrued (but not yet
    # paid) are "locked in" here at the OLD rate, and sales_at_last_commission is reset
    # to total_sales. This guarantees a rate change only affects NEW sales going forward,
    # never re-prices sales that already accrued under the previous rate.
    commission_carryover_amount = db.Column(db.Float, default=0.0)
    
    user = db.relationship('User', back_populates='store_profile', foreign_keys=[user_id])
    products = db.relationship('Product', back_populates='store', cascade='all, delete-orphan')

    @property
    def commission_due(self):
        """Total commission currently owed: locked-in carryover (at prior rates) plus
        new sales accrued since the last commission baseline, priced at the CURRENT rate."""
        new_sales = max((self.total_sales or 0.0) - (self.sales_at_last_commission or 0.0), 0.0)
        due = (self.commission_carryover_amount or 0.0) + new_sales * ((self.commission_percentage or 0.0) / 100.0)
        return round(max(due, 0.0), 2)

    def lock_in_commission_rate_change(self, new_percentage):
        """Call this BEFORE changing commission_percentage. Freezes whatever is owed
        under the current rate into commission_carryover_amount, then resets the sales
        baseline so the new rate only applies to sales made from this point forward."""
        new_sales = max((self.total_sales or 0.0) - (self.sales_at_last_commission or 0.0), 0.0)
        accrued_at_old_rate = new_sales * ((self.commission_percentage or 0.0) / 100.0)
        self.commission_carryover_amount = (self.commission_carryover_amount or 0.0) + accrued_at_old_rate
        self.sales_at_last_commission = self.total_sales
        self.commission_percentage = new_percentage

class Category(db.Model):
    __tablename__ = 'categories'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('categories.id', ondelete='CASCADE'), nullable=True)
    icon = db.Column(db.String(50), nullable=True) # e.g. FontAwesome class or image filename
    image = db.Column(db.String(255), nullable=True)
    
    # Self-referencing relationship for nesting
    children = db.relationship('Category', backref=db.backref('parent', remote_side=[id]), cascade='all, delete-orphan')
    products = db.relationship('Product', back_populates='category')

class Brand(db.Model):
    __tablename__ = 'brands'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False)
    logo = db.Column(db.String(255), nullable=True)
    description = db.Column(db.Text, nullable=True)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id', ondelete='SET NULL'), nullable=True)
    
    category = db.relationship('Category', backref='brands')
    products = db.relationship('Product', back_populates='brand')

class Product(db.Model):
    __tablename__ = 'products'
    
    id = db.Column(db.Integer, primary_key=True)
    seller_id = db.Column(db.Integer, db.ForeignKey('store_profiles.id', ondelete='CASCADE'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id', ondelete='SET NULL'), nullable=True)
    brand_id = db.Column(db.Integer, db.ForeignKey('brands.id', ondelete='SET NULL'), nullable=True)
    
    name = db.Column(db.String(200), nullable=False, index=True)
    slug = db.Column(db.String(200), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=False)
    
    # Store dynamic fields as JSON string or Text
    _specifications = db.Column('specifications', db.Text, default='{}')
    _features = db.Column('features', db.Text, default='[]')
    
    warranty = db.Column(db.String(100), nullable=True)
    dimensions = db.Column(db.String(100), nullable=True) # e.g. "10x5x2 cm"
    weight = db.Column(db.Float, default=0.0) # In kg
    sku = db.Column(db.String(50), unique=True, nullable=False, index=True)
    barcode = db.Column(db.String(50), nullable=True)
    qr_code = db.Column(db.String(255), nullable=True)
    
    base_price = db.Column(db.Float, nullable=False)
    discount_percent = db.Column(db.Float, default=0.0)
    offer_price = db.Column(db.Float, nullable=False)
    stock = db.Column(db.Integer, default=0)  # Base product stock (for products without variants)
    
    # Region availability — stored as JSON arrays of strings
    _available_countries = db.Column('available_countries', db.Text, default='[]')
    _available_states = db.Column('available_states', db.Text, default='[]')
    _available_districts = db.Column('available_districts', db.Text, default='[]')
    
    is_digital = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    shipping_charges = db.Column(db.Float, default=0.0)  # Kept for legacy; not editable by seller
    tax_percentage = db.Column(db.Float, default=0.0)    # Kept for legacy; not editable by seller
    delivery_days = db.Column(db.Integer, default=3)
    views = db.Column(db.Integer, default=0)
    clicks = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    store = db.relationship('StoreProfile', back_populates='products')
    category = db.relationship('Category', back_populates='products')
    brand = db.relationship('Brand', back_populates='products')
    images = db.relationship('ProductImage', back_populates='product', cascade='all, delete-orphan')
    variants = db.relationship('ProductVariant', back_populates='product', cascade='all, delete-orphan')
    reviews = db.relationship('Review', back_populates='product', cascade='all, delete-orphan')
    questions = db.relationship('QuestionAnswer', back_populates='product', cascade='all, delete-orphan')
    inventory_movements = db.relationship('InventoryMovement', back_populates='product', cascade='all, delete-orphan')
    recently_viewed = db.relationship('RecentlyViewed', back_populates='product', cascade='all, delete-orphan')
    wishlist_entries = db.relationship('Wishlist', back_populates='product', cascade='all, delete-orphan')

    @property
    def specifications(self):
        try:
            return json.loads(self._specifications)
        except Exception:
            return {}

    @specifications.setter
    def specifications(self, value):
        self._specifications = json.dumps(value)

    @property
    def features(self):
        try:
            return json.loads(self._features)
        except Exception:
            return []

    @features.setter
    def features(self, value):
        self._features = json.dumps(value)

    @property
    def available_countries(self):
        try:
            return json.loads(self._available_countries)
        except Exception:
            return []

    @available_countries.setter
    def available_countries(self, value):
        self._available_countries = json.dumps(value)

    @property
    def available_states(self):
        try:
            return json.loads(self._available_states)
        except Exception:
            return []

    @available_states.setter
    def available_states(self, value):
        self._available_states = json.dumps(value)

    @property
    def available_districts(self):
        try:
            return json.loads(self._available_districts)
        except Exception:
            return []

    @available_districts.setter
    def available_districts(self, value):
        self._available_districts = json.dumps(value)

    def is_available_in_address(self, address):
        """
        Check if this product is available for the given Address object.

        Matching strategy (applied in order, any match = available):
          1. If no regions configured at all → available everywhere.
          2. Exact normalised match     (case-insensitive, collapsed whitespace).
          3. Pincode / pincode-range    (numeric entries, e.g. "600001" or
                                         "600001-600100", compared against the
                                         customer's postal code).
          4. Phrase / boundary match    (entry appears as a whole word or
                                         phrase inside the field value, or vice
                                         versa — guards against partial-word
                                         false positives like "Salem" wrongly
                                         matching "Salemvakkam").
          5. Token-overlap match        (every word of the shorter string
                                         appears in the longer string).

        All relevant customer address fields are compared against every level
        (countries → states → districts/cities/pincodes), so partial names,
        abbreviations and composite values (e.g. "Salem District" vs "Salem")
        work correctly, while avoiding accidental substring false-positives.
        """
        countries  = self.available_countries
        states     = self.available_states
        districts  = self.available_districts

        # ── 1. No restrictions → ship everywhere ─────────────────────────────
        if not countries and not states and not districts:
            return True

        import re

        def _norm(s):
            """Lowercase + collapse all whitespace."""
            return re.sub(r'\s+', ' ', (s or '').strip().lower())

        def _tokens(s):
            return set(re.findall(r'[a-z0-9]+', _norm(s)))

        def _is_pincode_entry(entry):
            """True if *entry* looks like a postal code or postal code range."""
            e = (entry or '').strip()
            return bool(re.match(r'^\d{4,10}\s*-\s*\d{4,10}$', e) or re.match(r'^\d{4,10}$', e))

        def _pincode_matches(entry, postal_code):
            """Match an exact pincode or a numeric pincode range against the address's postal code."""
            digits = re.sub(r'\D', '', postal_code or '')
            if not digits:
                return False
            e = (entry or '').strip()
            if '-' in e:
                lo_raw, hi_raw = e.split('-', 1)
                lo, hi = re.sub(r'\D', '', lo_raw), re.sub(r'\D', '', hi_raw)
                if not lo or not hi:
                    return False
                try:
                    return int(lo) <= int(digits) <= int(hi)
                except ValueError:
                    return False
            entry_digits = re.sub(r'\D', '', e)
            return bool(entry_digits) and entry_digits == digits

        def _phrase_match(e, f):
            """
            Whole word/phrase containment in either direction, guarding against
            partial-word false positives (e.g. "Salem" must not match
            "Salemvakkam"). Very short strings (<3 chars) are excluded from
            this strategy since they are prone to spurious matches.
            """
            if len(e) < 3 or len(f) < 3:
                return False
            shorter, longer = (e, f) if len(e) <= len(f) else (f, e)
            pattern = r'(?<![a-z0-9])' + re.escape(shorter) + r'(?![a-z0-9])'
            return re.search(pattern, longer) is not None

        def _matches(entry, field_value):
            """
            Return True if *entry* (from product config) matches *field_value*
            (from customer address) using multiple strategies.
            """
            e = _norm(entry)
            f = _norm(field_value)
            if not e or not f:
                return False
            # Strategy 1 – exact
            if e == f:
                return True
            # Strategy 2 – whole word / phrase containment (boundary-safe)
            if _phrase_match(e, f):
                return True
            # Strategy 3 – token overlap (all words of shorter appear in longer)
            et = _tokens(entry)
            ft = _tokens(field_value)
            if et and ft:
                shorter, longer = (et, ft) if len(et) <= len(ft) else (ft, et)
                if shorter and shorter.issubset(longer):
                    return True
            return False

        # ── Collect all customer address candidate strings per level ──────────
        # Countries: use the country field (default "India")
        addr_countries = [
            address.country,
        ]

        # States: state field
        addr_states = [
            address.state,
        ]

        # Districts / sub-regions: every field that could represent a district
        addr_districts = [
            address.district,          # explicit CID district
            address.city,              # standard city field
            address.village_city,      # CID village/city
            address.taluk_name,        # taluk = sub-district
            address.post_name,         # post office area
        ]
        # Remove blanks
        addr_countries = [v for v in addr_countries if v]
        addr_states    = [v for v in addr_states if v]
        addr_districts = [v for v in addr_districts if v]

        addr_postal_code = getattr(address, 'postalCode', None)

        def _level_matches(region_list, addr_candidates, postal_code=None):
            """Return True if any entry in region_list matches any candidate."""
            for entry in region_list:
                if _is_pincode_entry(entry):
                    if postal_code and _pincode_matches(entry, postal_code):
                        return True
                    continue
                for candidate in addr_candidates:
                    if _matches(entry, candidate):
                        return True
            return False

        # ── 2. Country check ──────────────────────────────────────────────────
        if countries and _level_matches(countries, addr_countries):
            return True

        # ── 3. State check ────────────────────────────────────────────────────
        if states and _level_matches(states, addr_states):
            return True

        # ── 4. District / city / pincode check ──────────────────────────────
        if districts and _level_matches(districts, addr_districts, addr_postal_code):
            return True

        return False

    @property
    def average_rating(self):
        ratings = [r.rating for r in self.reviews]
        if not ratings:
            return 0.0
        return round(sum(ratings) / len(ratings), 1)

    @property
    def is_out_of_stock(self):
        """Return True if the product has no available stock (considering variants)."""
        if self.variants:
            return all((v.stock or 0) <= 0 for v in self.variants)
        return (self.stock or 0) <= 0

    @property
    def main_image(self):
        primary = next((img.image_path for img in self.images if img.is_primary), None)
        if primary:
            return primary
        return self.images[0].image_path if self.images else 'placeholder.jpg'

class ProductImage(db.Model):
    __tablename__ = 'product_images'
    
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='CASCADE'), nullable=False)
    image_path = db.Column(db.String(255), nullable=False)
    is_primary = db.Column(db.Boolean, default=False)
    
    product = db.relationship('Product', back_populates='images')

class ProductVariant(db.Model):
    __tablename__ = 'product_variants'
    
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='CASCADE'), nullable=False)
    sku = db.Column(db.String(50), unique=True, nullable=False)
    stock = db.Column(db.Integer, default=0)
    price = db.Column(db.Float, nullable=False)
    discount_price = db.Column(db.Float, nullable=True)
    
    # Common attributes
    color = db.Column(db.String(50), nullable=True)
    size = db.Column(db.String(50), nullable=True)
    ram = db.Column(db.String(50), nullable=True)
    storage = db.Column(db.String(50), nullable=True)
    weight = db.Column(db.Float, nullable=True)
    
    # Extensible field
    _custom_attributes = db.Column('custom_attributes', db.Text, default='{}')
    image_path = db.Column(db.String(255), nullable=True)
    
    product = db.relationship('Product', back_populates='variants')

    @property
    def custom_attributes(self):
        try:
            return json.loads(self._custom_attributes)
        except Exception:
            return {}

    @custom_attributes.setter
    def custom_attributes(self, value):
        self._custom_attributes = json.dumps(value)

class CartItem(db.Model):
    __tablename__ = 'cart'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='CASCADE'), nullable=False)
    variant_id = db.Column(db.Integer, db.ForeignKey('product_variants.id', ondelete='SET NULL'), nullable=True)
    quantity = db.Column(db.Integer, default=1, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', back_populates='cart_items')
    product = db.relationship('Product')
    variant = db.relationship('ProductVariant')

class Wishlist(db.Model):
    __tablename__ = 'wishlist'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='CASCADE'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', back_populates='wishlist')
    product = db.relationship('Product', back_populates='wishlist_entries')

class Address(db.Model):
    __tablename__ = 'addresses'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    title = db.Column(db.String(50), nullable=False) # "Home", "Office"
    fullName = db.Column(db.String(100), nullable=False)
    addressLine1 = db.Column(db.String(255), nullable=False)
    addressLine2 = db.Column(db.String(255), nullable=True)
    city = db.Column(db.String(100), nullable=False)
    state = db.Column(db.String(100), nullable=False)
    postalCode = db.Column(db.String(20), nullable=False)
    country = db.Column(db.String(100), nullable=False, default='India')
    phone = db.Column(db.String(20), nullable=False)
    is_default = db.Column(db.Boolean, default=False)
    
    # CID Address fields
    door_no = db.Column(db.String(100), nullable=True)
    street = db.Column(db.String(255), nullable=True)
    village_city = db.Column(db.String(255), nullable=True)
    post_name = db.Column(db.String(100), nullable=True)
    taluk_name = db.Column(db.String(100), nullable=True)
    district = db.Column(db.String(100), nullable=True)
    landmark = db.Column(db.String(255), nullable=True)
    contact_number = db.Column(db.String(50), nullable=True)
    
    user = db.relationship('User', back_populates='addresses', foreign_keys=[user_id])

class Order(db.Model):
    __tablename__ = 'orders'
    
    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(50), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    address_id = db.Column(db.Integer, db.ForeignKey('addresses.id', ondelete='SET NULL'), nullable=True)
    
    # Financial fields
    total_amount = db.Column(db.Float, nullable=False)
    discount_amount = db.Column(db.Float, default=0.0)
    shipping_charges = db.Column(db.Float, default=0.0)
    tax_amount = db.Column(db.Float, default=0.0)
    grand_total = db.Column(db.Float, nullable=False)
    
    # Workflow status
    status = db.Column(db.String(30), default='Pending', index=True)
    # Pending -> Confirmed -> Packed -> Shipped -> Out For Delivery -> Delivered -> Cancelled -> Returned -> Refunded
    
    coupon_id = db.Column(db.Integer, db.ForeignKey('coupons.id', ondelete='SET NULL'), nullable=True)
    tracking_number = db.Column(db.String(100), nullable=True)
    courier_partner = db.Column(db.String(100), nullable=True)
    
    wallet_deduction = db.Column(db.Float, default=0.0)
    reward_points_deduction = db.Column(db.Float, default=0.0)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', back_populates='orders')
    address = db.relationship('Address')
    items = db.relationship('OrderItem', back_populates='order', cascade='all, delete-orphan')
    payment = db.relationship('Payment', uselist=False, back_populates='order', cascade='all, delete-orphan')
    refund = db.relationship('Refund', uselist=False, back_populates='order', cascade='all, delete-orphan')

class OrderItem(db.Model):
    __tablename__ = 'order_items'
    
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id', ondelete='CASCADE'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='SET NULL'), nullable=True)
    variant_id = db.Column(db.Integer, db.ForeignKey('product_variants.id', ondelete='SET NULL'), nullable=True)
    
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Float, nullable=False)
    total_price = db.Column(db.Float, nullable=False)
    
    # Backup static values in case the product gets deleted/modified later
    product_name = db.Column(db.String(200), nullable=False)
    variant_details = db.Column(db.String(255), nullable=True)
    
    order = db.relationship('Order', back_populates='items')
    product = db.relationship('Product')
    variant = db.relationship('ProductVariant')
    return_request = db.relationship('ReturnRequest', uselist=False, back_populates='order_item', cascade='all, delete-orphan')

class Payment(db.Model):
    __tablename__ = 'payments'
    
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id', ondelete='CASCADE'), nullable=False, unique=True)
    payment_method = db.Column(db.String(50), nullable=False) # "UPI", "Credit Card", "Wallet", "COD", "BNPL"
    transaction_id = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(30), default='Pending') # "Pending", "Completed", "Failed", "Refunded"
    amount = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # UPI transaction screenshot and contact info
    screenshot_path = db.Column(db.String(255), nullable=True)
    contact_number = db.Column(db.String(50), nullable=True)
    description = db.Column(db.Text, nullable=True)
    
    order = db.relationship('Order', back_populates='payment', foreign_keys=[order_id])

class Coupon(db.Model):
    __tablename__ = 'coupons'
    
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False, index=True)
    discount_type = db.Column(db.String(20), nullable=False) # "flat" or "percentage"
    value = db.Column(db.Float, nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id', ondelete='CASCADE'), nullable=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='CASCADE'), nullable=True)
    
    usage_limit = db.Column(db.Integer, default=100)
    usage_count = db.Column(db.Integer, default=0)
    expiry_date = db.Column(db.DateTime, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    min_order_amount = db.Column(db.Float, default=0.0)
    
    category = db.relationship('Category')
    product = db.relationship('Product')

class Review(db.Model):
    __tablename__ = 'reviews'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='CASCADE'), nullable=False)
    rating = db.Column(db.Integer, nullable=False) # 1 to 5
    title = db.Column(db.String(100), nullable=True)
    content = db.Column(db.Text, nullable=False)
    image_path = db.Column(db.String(255), nullable=True)
    video_path = db.Column(db.String(255), nullable=True)
    
    helpful_votes = db.Column(db.Integer, default=0)
    report_count = db.Column(db.Integer, default=0)
    is_verified_purchase = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', back_populates='reviews')
    product = db.relationship('Product', back_populates='reviews')
    replies = db.relationship('ReviewReply', back_populates='review', cascade='all, delete-orphan')

class ReviewReply(db.Model):
    __tablename__ = 'review_replies'
    
    id = db.Column(db.Integer, primary_key=True)
    review_id = db.Column(db.Integer, db.ForeignKey('reviews.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    reply_content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    review = db.relationship('Review', back_populates='replies')
    user = db.relationship('User')

class QuestionAnswer(db.Model):
    __tablename__ = 'question_answers'
    
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    question = db.Column(db.Text, nullable=False)
    answer = db.Column(db.Text, nullable=True)
    answered_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    answered_at = db.Column(db.DateTime, nullable=True)
    
    product = db.relationship('Product', back_populates='questions')
    user = db.relationship('User', foreign_keys=[user_id])
    replier = db.relationship('User', foreign_keys=[answered_by])

class WalletTransaction(db.Model):
    __tablename__ = 'wallet_transactions'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    type = db.Column(db.String(20), nullable=False) # "credit" or "debit"
    description = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', back_populates='wallet_transactions')

class RewardPoint(db.Model):
    __tablename__ = 'reward_points'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    points = db.Column(db.Integer, nullable=False)
    type = db.Column(db.String(20), nullable=False) # "credit" or "debit"
    description = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', back_populates='reward_points')

class RecentlyViewed(db.Model):
    __tablename__ = 'recently_viewed'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='CASCADE'), nullable=False)
    viewed_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    user = db.relationship('User', back_populates='recently_viewed')
    product = db.relationship('Product', back_populates='recently_viewed')

class SearchHistory(db.Model):
    __tablename__ = 'search_history'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=True)
    query = db.Column(db.String(255), nullable=False)
    searched_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', back_populates='search_history')

class Notification(db.Model):
    __tablename__ = 'notifications'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    type = db.Column(db.String(50), default='general') # 'order', 'offer', 'alert'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', back_populates='notifications')

class SupportTicket(db.Model):
    __tablename__ = 'support_tickets'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    subject = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(50), nullable=False) # e.g. "Payment", "Shipping", "Refund"
    status = db.Column(db.String(30), default='Open') # "Open", "In Progress", "Closed"
    priority = db.Column(db.String(20), default='Medium') # "Low", "Medium", "High"
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    user = db.relationship('User', back_populates='support_tickets')
    messages = db.relationship('SupportMessage', back_populates='ticket', cascade='all, delete-orphan')

class SupportMessage(db.Model):
    __tablename__ = 'support_messages'
    
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('support_tickets.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    ticket = db.relationship('SupportTicket', back_populates='messages')
    user = db.relationship('User')

class Warehouse(db.Model):
    __tablename__ = 'warehouses'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    location = db.Column(db.String(255), nullable=False)
    code = db.Column(db.String(50), unique=True, nullable=False)

class InventoryMovement(db.Model):
    __tablename__ = 'inventory_movements'
    
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='CASCADE'), nullable=False)
    variant_id = db.Column(db.Integer, db.ForeignKey('product_variants.id', ondelete='SET NULL'), nullable=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id', ondelete='CASCADE'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    type = db.Column(db.String(20), nullable=False) # "in" or "out"
    description = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    product = db.relationship('Product', back_populates='inventory_movements')
    variant = db.relationship('ProductVariant')
    warehouse = db.relationship('Warehouse')

class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    role = db.Column(db.String(50), nullable=True)
    action = db.Column(db.String(100), nullable=False) # e.g. "LOGIN", "CHECKOUT", "UPDATE_PRODUCT"
    table_name = db.Column(db.String(100), nullable=True)
    row_id = db.Column(db.Integer, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)
    details = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User')

class SystemSetting(db.Model):
    __tablename__ = 'settings'
    
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=False)
    group = db.Column(db.String(50), default='general') # 'general', 'tax', 'shipping', 'api'

class Banner(db.Model):
    __tablename__ = 'banners'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=True)
    subtitle = db.Column(db.String(150), nullable=True)
    image_path = db.Column(db.String(255), nullable=False)
    link_url = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    order_seq = db.Column(db.Integer, default=0)
    expires_at = db.Column(db.DateTime, nullable=True)

class ReturnRequest(db.Model):
    __tablename__ = 'returns'
    
    id = db.Column(db.Integer, primary_key=True)
    order_item_id = db.Column(db.Integer, db.ForeignKey('order_items.id', ondelete='CASCADE'), nullable=False, unique=True)
    reason = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(30), default='Pending') # "Pending", "Approved", "Rejected"
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    order_item = db.relationship('OrderItem', back_populates='return_request')
    refund = db.relationship('Refund', uselist=False, back_populates='return_request', cascade='all, delete-orphan')

class Refund(db.Model):
    __tablename__ = 'refunds'
    
    id = db.Column(db.Integer, primary_key=True)
    return_request_id = db.Column(db.Integer, db.ForeignKey('returns.id', ondelete='CASCADE'), nullable=True, unique=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id', ondelete='CASCADE'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(30), default='Pending') # "Pending", "Completed"
    transaction_id = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    return_request = db.relationship('ReturnRequest', back_populates='refund')
    order = db.relationship('Order', back_populates='refund')

class SellerNotice(db.Model):
    __tablename__ = 'seller_notices'
    
    id = db.Column(db.Integer, primary_key=True)
    store_id = db.Column(db.Integer, db.ForeignKey('store_profiles.id', ondelete='CASCADE'), nullable=True) # NULL means all sellers
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    store = db.relationship('StoreProfile', backref=db.backref('notices', lazy='dynamic', cascade='all, delete-orphan'))

class SellerFeedback(db.Model):
    __tablename__ = 'seller_feedback'
    
    id = db.Column(db.Integer, primary_key=True)
    store_id = db.Column(db.Integer, db.ForeignKey('store_profiles.id', ondelete='CASCADE'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    store = db.relationship('StoreProfile', backref=db.backref('feedback', lazy='dynamic', cascade='all, delete-orphan'))

class CommissionPayment(db.Model):
    __tablename__ = 'commission_payments'
    
    id = db.Column(db.Integer, primary_key=True)
    store_id = db.Column(db.Integer, db.ForeignKey('store_profiles.id', ondelete='CASCADE'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    screenshot = db.Column(db.String(255), nullable=True)
    transaction_id = db.Column(db.String(100), nullable=False) # UTR or reference number
    contact_number = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(30), default='In progress') # 'In progress', 'Paid', 'Rejected'
    rejected_reason = db.Column(db.Text, nullable=True)
    rejected_at = db.Column(db.DateTime, nullable=True)
    rejected_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    store = db.relationship('StoreProfile', backref=db.backref('commission_payments', lazy='dynamic', cascade='all, delete-orphan'))
    rejected_by_user = db.relationship('User', foreign_keys=[rejected_by])

class Complaint(db.Model):
    __tablename__ = 'complaints'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id', ondelete='CASCADE'), nullable=False)
    screenshot = db.Column(db.String(255), nullable=True)
    details = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(30), default='Pending') # 'Pending', 'Resolved'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref=db.backref('complaints', lazy='dynamic', cascade='all, delete-orphan'))
    order = db.relationship('Order', backref=db.backref('complaints', lazy='dynamic', cascade='all, delete-orphan'))

# ==================== NEW MODELS FOR UPGRADE ====================

class CommissionReport(db.Model):
    """Seller commission payment report/complaint"""
    __tablename__ = 'commission_reports'
    
    id = db.Column(db.Integer, primary_key=True)
    store_id = db.Column(db.Integer, db.ForeignKey('store_profiles.id', ondelete='CASCADE'), nullable=False)
    commission_payment_id = db.Column(db.Integer, db.ForeignKey('commission_payments.id', ondelete='SET NULL'), nullable=True)
    explanation = db.Column(db.Text, nullable=False)
    proof_file = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(30), default='Open') # 'Open', 'Resolved', 'Closed'
    admin_reply = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    store = db.relationship('StoreProfile', backref=db.backref('commission_reports', lazy='dynamic'))
    commission_payment = db.relationship('CommissionPayment', backref=db.backref('reports', lazy='dynamic'))

class SubAdminActivity(db.Model):
    """Track sub admin activity for audit"""
    __tablename__ = 'sub_admin_activities'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    action = db.Column(db.String(200), nullable=False)
    details = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref=db.backref('sub_admin_activities', lazy='dynamic', cascade='all, delete-orphan', passive_deletes=True))


# ==================== MULTI-SERVER INFRASTRUCTURE MODELS ====================

class ServerInstance(db.Model):
    """Multi-server infrastructure registry & health tracking"""
    __tablename__ = 'server_instances'
    
    id = db.Column(db.Integer, primary_key=True)
    server_id = db.Column(db.String(100), unique=True, nullable=False, index=True) # e.g. "srv-asia-south-1a"
    name = db.Column(db.String(100), nullable=False) # e.g. "VKShop Primary Render 1"
    provider = db.Column(db.String(50), default='Render') # "Render", "AWS", "Self-Hosted", "GCP"
    region = db.Column(db.String(50), default='India') # "India", "Singapore", "US-East"
    ip_address = db.Column(db.String(45), nullable=True)
    api_endpoint = db.Column(db.String(255), nullable=False) # e.g. "https://vkshop-srv1.onrender.com"
    health_endpoint = db.Column(db.String(255), default='/ready')
    
    weight = db.Column(db.Integer, default=100) # Load balancer routing weight
    status = db.Column(db.String(30), default='ONLINE', index=True) # 'ONLINE', 'DEGRADED', 'UNHEALTHY', 'OFFLINE'
    is_maintenance = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    
    cpu_usage = db.Column(db.Float, default=0.0) # CPU %
    memory_usage = db.Column(db.Float, default=0.0) # Memory %
    active_requests = db.Column(db.Integer, default=0)
    requests_per_min = db.Column(db.Integer, default=0)
    avg_latency_ms = db.Column(db.Float, default=0.0)
    error_rate = db.Column(db.Float, default=0.0) # Error %
    consecutive_failures = db.Column(db.Integer, default=0)
    
    last_heartbeat = db.Column(db.DateTime, default=datetime.utcnow)
    last_successful_request = db.Column(db.DateTime, default=datetime.utcnow)
    version = db.Column(db.String(50), default='2.0.0')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ServerMetric(db.Model):
    """Historical telemetry metric points per server node"""
    __tablename__ = 'server_metrics'
    
    id = db.Column(db.Integer, primary_key=True)
    server_id = db.Column(db.String(100), db.ForeignKey('server_instances.server_id', ondelete='CASCADE'), nullable=False)
    cpu_pct = db.Column(db.Float, default=0.0)
    memory_pct = db.Column(db.Float, default=0.0)
    latency_ms = db.Column(db.Float, default=0.0)
    requests_per_sec = db.Column(db.Float, default=0.0)
    error_count_5xx = db.Column(db.Integer, default=0)
    recorded_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    server = db.relationship('ServerInstance', backref=db.backref('metrics', lazy='dynamic', cascade='all, delete-orphan'))