from flask import Blueprint, request, jsonify
from flask_login import current_user
from database import db
from models import Product, ProductVariant, Category, CartItem, Wishlist, SearchHistory
import json

api_bp = Blueprint('api', __name__)

@api_bp.route('/search-suggestions')
def search_suggestions():
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify([])
        
    from services.storage import resolve_image_url
    products = Product.query.filter(Product.name.like(f"%{q}%"), Product.is_active == True).limit(5).all()
    results = []
    
    for p in products:
        results.append({
            'label': p.name,
            'slug': p.slug,
            'price': p.offer_price,
            'image_url': resolve_image_url(p.main_image, default_category='products')
        })
        
    return jsonify(results)

@api_bp.route('/product-variant-details')
def variant_details():
    prod_id = request.args.get('product_id', type=int)
    color = request.args.get('color', '').strip()
    size = request.args.get('size', '').strip()
    ram = request.args.get('ram', '').strip()
    storage = request.args.get('storage', '').strip()
    
    if not (color or size or ram or storage):
        product = Product.query.get(prod_id)
        if product:
            from services.storage import resolve_image_url
            stock_count = product.stock if (product.stock and product.stock > 0) else sum((v.stock or 0) for v in product.variants)
            return jsonify({
                'success': True,
                'is_base': True,
                'variant_id': None,
                'price': product.offer_price,
                'stock': stock_count,
                'sku': product.sku,
                'image_url': resolve_image_url(product.main_image, default_category='products')
            })

    query = ProductVariant.query.filter_by(product_id=prod_id)
    if color:
        query = query.filter_by(color=color)
    if size:
        query = query.filter_by(size=size)
    if ram:
        query = query.filter_by(ram=ram)
    if storage:
        query = query.filter_by(storage=storage)
        
    variant = query.first()
    if variant:
        from services.storage import resolve_image_url
        return jsonify({
            'success': True,
            'is_base': False,
            'variant_id': variant.id,
            'price': variant.price,
            'stock': variant.stock,
            'sku': variant.sku,
            'image_url': resolve_image_url(variant.image_path, default_category='products') if variant.image_path else ""
        })
        
    return jsonify({
        'success': False,
        'message': 'No variant matching selected options.'
    })

@api_bp.route('/cart/items-count')
def cart_items_count():
    if not current_user.is_authenticated:
        return jsonify({'count': 0})
    count = db.session.query(db.func.sum(CartItem.quantity)).filter_by(user_id=current_user.id).scalar() or 0
    return jsonify({'count': count})

@api_bp.route('/wishlist/toggle/<int:product_id>', methods=['POST'])
def wishlist_toggle(product_id):
    if not current_user.is_authenticated:
        return jsonify({'success': False, 'message': 'Authentication required.'}), 401
        
    w = Wishlist.query.filter_by(user_id=current_user.id, product_id=product_id).first()
    if w:
        db.session.delete(w)
        db.session.commit()
        return jsonify({'success': True, 'action': 'removed', 'message': 'Removed from wishlist.'})
    else:
        new_w = Wishlist(user_id=current_user.id, product_id=product_id)
        db.session.add(new_w)
        db.session.commit()
        return jsonify({'success': True, 'action': 'added', 'message': 'Added to wishlist.'})

# ==================== MOBILE & ANDROID REST API ENDPOINTS ====================

@api_bp.route('/products', methods=['GET'])
def get_products():
    """Paginated product catalog for Android App & REST Clients."""
    from services.storage import resolve_image_url
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    q = request.args.get('q', '').strip()
    cat_id = request.args.get('category_id', type=int)

    query = Product.query.filter_by(is_active=True)
    if q:
        query = query.filter(Product.name.ilike(f"%{q}%"))
    if cat_id:
        query = query.filter_by(category_id=cat_id)

    pagination = query.order_by(Product.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    items = []
    for p in pagination.items:
        items.append({
            'id': p.id,
            'name': p.name,
            'slug': p.slug,
            'base_price': p.base_price,
            'offer_price': p.offer_price,
            'discount_percent': p.discount_percent,
            'image_url': resolve_image_url(p.main_image),
            'rating': p.average_rating,
            'in_stock': not p.is_out_of_stock
        })
    return jsonify({
        'success': True,
        'page': page,
        'pages': pagination.pages,
        'total': pagination.total,
        'products': items
    })

@api_bp.route('/products/<int:product_id>', methods=['GET'])
def get_product_detail(product_id):
    """Detailed product information with image gallery, specs & variants."""
    from services.storage import resolve_image_url
    p = Product.query.get_or_404(product_id)
    images = [resolve_image_url(img.image_path) for img in p.images] or [resolve_image_url(p.main_image)]
    variants = []
    for v in p.variants:
        variants.append({
            'id': v.id,
            'color': v.color,
            'size': v.size,
            'ram': v.ram,
            'storage': v.storage,
            'price': v.price,
            'stock': v.stock
        })
    return jsonify({
        'success': True,
        'product': {
            'id': p.id,
            'name': p.name,
            'description': p.description,
            'base_price': p.base_price,
            'offer_price': p.offer_price,
            'discount_percent': p.discount_percent,
            'rating': p.average_rating,
            'images': images,
            'variants': variants,
            'specifications': p.specifications,
            'features': p.features,
            'in_stock': not p.is_out_of_stock
        }
    })

@api_bp.route('/categories', methods=['GET'])
def get_categories():
    """Return category hierarchy for mobile navigation."""
    from services.storage import resolve_image_url
    categories = Category.query.filter(Category.parent_id == None).all()
    res = []
    for c in categories:
        res.append({
            'id': c.id,
            'name': c.name,
            'slug': c.slug,
            'icon': c.icon,
            'image_url': resolve_image_url(c.image),
            'children': [{'id': ch.id, 'name': ch.name, 'slug': ch.slug} for ch in c.children]
        })
    return jsonify({'success': True, 'categories': res})

@api_bp.route('/storage/presigned-upload', methods=['POST'])
def generate_presigned_upload():
    """Generates direct S3 upload URL for mobile & web file upload controls."""
    data = request.get_json(silent=True) or {}
    category = data.get('category', 'products')
    original_filename = data.get('filename', 'image.jpg')
    
    from services.storage import storage_service, generate_object_key
    key = generate_object_key(category, original_filename)
    url = storage_service.generate_presigned_upload_url(key)
    
    return jsonify({
        'success': bool(url),
        'object_key': key,
        'upload_url': url or f"/api/storage/upload-direct/{key}",
        'public_url': storage_service.get_public_url(key)
    })

