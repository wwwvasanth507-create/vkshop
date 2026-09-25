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
        
    # Query database for matching product names
    products = Product.query.filter(Product.name.like(f"%{q}%"), Product.is_active == True).limit(5).all()
    results = []
    
    for p in products:
        results.append({
            'label': p.name,
            'slug': p.slug,
            'price': p.offer_price,
            'image': p.main_image
        })
        
    return jsonify(results)

@api_bp.route('/product-variant-details')
def variant_details():
    prod_id = request.args.get('product_id', type=int)
    color = request.args.get('color', '').strip()
    size = request.args.get('size', '').strip()
    ram = request.args.get('ram', '').strip()
    storage = request.args.get('storage', '').strip()
    
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
        return jsonify({
            'success': True,
            'variant_id': variant.id,
            'price': variant.price,
            'stock': variant.stock,
            'sku': variant.sku,
            'image_path': variant.image_path if variant.image_path else ""
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
