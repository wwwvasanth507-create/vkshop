from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import current_user
from database import db
from models import Product, ProductImage, ProductVariant, Category, Brand, Review, QuestionAnswer, RecentlyViewed, SearchHistory, Banner, User, StoreProfile
from datetime import datetime

main_bp = Blueprint('main', __name__)

def get_interested_products(user_id=None, limit=5):
    # If not logged in, return the top 5 products by views/clicks/ratings
    if not user_id:
        return Product.query.filter_by(is_active=True).order_by((Product.views + Product.clicks).desc()).limit(limit).all()
    
    from models import Wishlist, CartItem, Order, OrderItem, RecentlyViewed, SearchHistory
    
    # 1. Fetch user's wishlist categories
    wishlist_items = Wishlist.query.filter_by(user_id=user_id).all()
    wishlist_cat_ids = [item.product.category_id for item in wishlist_items if item.product and item.product.category_id]
    
    # 2. Fetch user's cart categories
    cart_items = CartItem.query.filter_by(user_id=user_id).all()
    cart_cat_ids = [item.product.category_id for item in cart_items if item.product and item.product.category_id]
    
    # 3. Fetch user's order categories
    orders = Order.query.filter_by(user_id=user_id).filter(Order.status != 'Cancelled').all()
    order_cat_ids = []
    for o in orders:
        for item in o.items:
            if item.product and item.product.category_id:
                order_cat_ids.append(item.product.category_id)
                
    # 4. Fetch user's recently viewed categories
    recent_views = RecentlyViewed.query.filter_by(user_id=user_id).order_by(RecentlyViewed.viewed_at.desc()).limit(20).all()
    recent_cat_ids = [rv.product.category_id for rv in recent_views if rv.product and rv.product.category_id]
    
    # 5. Fetch categories matching search history
    searches = db.session.query(SearchHistory).filter_by(user_id=user_id).order_by(SearchHistory.searched_at.desc()).limit(10).all()
    search_cat_ids = []
    for s in searches:
        term = s.query.strip().lower()
        if term:
            matching_cats = Category.query.filter(Category.name.ilike(f'%{term}%')).all()
            search_cat_ids.extend([c.id for c in matching_cats])
            
    # Calculate category preference scores
    # Weights: Cart (5), Wishlist (4), Order (4), Recently Viewed (3), Search (2)
    scores = {}
    for cat_id in cart_cat_ids:
        scores[cat_id] = scores.get(cat_id, 0) + 5
    for cat_id in wishlist_cat_ids:
        scores[cat_id] = scores.get(cat_id, 0) + 4
    for cat_id in order_cat_ids:
        scores[cat_id] = scores.get(cat_id, 0) + 4
    for cat_id in recent_cat_ids:
        scores[cat_id] = scores.get(cat_id, 0) + 3
    for cat_id in search_cat_ids:
        scores[cat_id] = scores.get(cat_id, 0) + 2
        
    # Sort categories by preference score
    sorted_cats = [cat_id for cat_id, score in sorted(scores.items(), key=lambda x: x[1], reverse=True)]
    
    # Exclude products the user already has in wishlist or cart or already purchased
    exclude_prod_ids = set()
    exclude_prod_ids.update(item.product_id for item in wishlist_items if item.product_id)
    exclude_prod_ids.update(item.product_id for item in cart_items if item.product_id)
    for o in orders:
        for item in o.items:
            if item.product_id:
                exclude_prod_ids.add(item.product_id)
                
    recommended_products = []
    
    # Fetch top active products from preferred categories
    if sorted_cats:
        query = Product.query.filter(Product.category_id.in_(sorted_cats), Product.is_active == True)
        if exclude_prod_ids:
            query = query.filter(~Product.id.in_(exclude_prod_ids))
            
        candidate_products = query.limit(50).all()
        # Sort in Python by (category_score * 100) + views + clicks
        candidate_products.sort(
            key=lambda p: (scores.get(p.category_id, 0) * 100) + (p.views or 0) + (p.clicks or 0),
            reverse=True
        )
        recommended_products = candidate_products[:limit]
        
    # If we don't have enough recommendations, fill the rest with popular active products
    if len(recommended_products) < limit:
        needed = limit - len(recommended_products)
        existing_ids = {p.id for p in recommended_products}
        fill_query = Product.query.filter_by(is_active=True)
        if existing_ids:
            fill_query = fill_query.filter(~Product.id.in_(existing_ids))
        fill_products = fill_query.order_by((Product.views + Product.clicks).desc()).limit(needed).all()
        recommended_products.extend(fill_products)
        
    return recommended_products[:limit]

@main_bp.route('/')
def index():
    # Fetch active non-expired carousel banners
    now = datetime.utcnow()
    banners = Banner.query.filter(
        Banner.is_active == True,
        (Banner.expires_at == None) | (Banner.expires_at > now)
    ).order_by(Banner.order_seq).all()
    
    # Categories (cached in-memory)
    from app import get_cached_categories
    categories = get_cached_categories()
    
    # Deals, Best Sellers, and New Arrivals
    featured_products = Product.query.filter_by(is_active=True).limit(8).all()
    trending_products = Product.query.filter_by(is_active=True).order_by(Product.created_at.desc()).limit(8).all()
    
    # Recommendations (Auto-learned interested products)
    user_id = current_user.id if current_user.is_authenticated else None
    interested_products = get_interested_products(user_id=user_id, limit=5)
    
    # Recently viewed for logged-in users
    recent_items = []
    if current_user.is_authenticated:
        recent_views = RecentlyViewed.query.filter_by(user_id=current_user.id).order_by(RecentlyViewed.viewed_at.desc()).limit(8).all()
        recent_items = [rv.product for rv in recent_views if rv.product and rv.product.is_active]
        
    return render_template(
        'main/index.html',
        banners=banners,
        categories=categories,
        featured=featured_products,
        trending=trending_products,
        interested=interested_products,
        recent=recent_items
    )

@main_bp.route('/product/<slug>')
def product_detail(slug):
    product = Product.query.filter_by(slug=slug, is_active=True).first_or_404()
    
    # Track Product Views Analytics
    product.views += 1
    db.session.commit()
    
    # Save to recently viewed
    if current_user.is_authenticated:
        existing_view = RecentlyViewed.query.filter_by(user_id=current_user.id, product_id=product.id).first()
        if existing_view:
            existing_view.viewed_at = datetime.utcnow()
        else:
            new_view = RecentlyViewed(user_id=current_user.id, product_id=product.id)
            db.session.add(new_view)
        db.session.commit()
        
    # Get reviews
    reviews = Review.query.filter_by(product_id=product.id).order_by(Review.created_at.desc()).all()
    
    # Get questions
    questions = QuestionAnswer.query.filter_by(product_id=product.id).order_by(QuestionAnswer.created_at.desc()).all()
    
    # Find related products (same category)
    related = Product.query.filter(Product.category_id == product.category_id, Product.id != product.id, Product.is_active == True).limit(4).all()
    
    return render_template(
        'main/product_detail.html',
        product=product,
        reviews=reviews,
        questions=questions,
        related=related
    )

@main_bp.route('/product/click/<int:product_id>')
def track_click(product_id):
    product = Product.query.get_or_404(product_id)
    # Increment Click Count
    product.clicks += 1
    db.session.commit()
    return redirect(url_for('main.product_detail', slug=product.slug))

@main_bp.route('/category/<slug>')
def category_detail(slug):
    category = Category.query.filter_by(slug=slug).first_or_404()
    
    # Filters
    brand_id = request.args.get('brand', type=int)
    min_price = request.args.get('min_price', type=float)
    max_price = request.args.get('max_price', type=float)
    sort_by = request.args.get('sort', 'popular')
    
    query = Product.query.filter_by(category_id=category.id, is_active=True)
    
    if brand_id:
        query = query.filter_by(brand_id=brand_id)
    if min_price is not None:
        query = query.filter(Product.offer_price >= min_price)
    if max_price is not None:
        query = query.filter(Product.offer_price <= max_price)
        
    if sort_by == 'price_low':
        query = query.order_by(Product.offer_price.asc())
    elif sort_by == 'price_high':
        query = query.order_by(Product.offer_price.desc())
    elif sort_by == 'newest':
        query = query.order_by(Product.created_at.desc())
        
    products = query.all()
    brands = Brand.query.all()
    
    return render_template(
        'main/category.html',
        category=category,
        products=products,
        brands=brands,
        selected_brand=brand_id,
        min_price=min_price,
        max_price=max_price,
        sort_by=sort_by
    )

@main_bp.route('/search')
def search():
    q = request.args.get('q', '').strip()
    category_id = request.args.get('category', type=int)
    brand_id = request.args.get('brand', type=int)
    sort_by = request.args.get('sort', 'relevance')
    
    # Save search query
    if q:
        history = SearchHistory(
            user_id=current_user.id if current_user.is_authenticated else None,
            query=q
        )
        db.session.add(history)
        db.session.commit()
        
    query = Product.query.filter(Product.is_active == True)
    
    if q:
        # Typo tolerance / basic search expansion
        query = query.filter((Product.name.like(f"%{q}%")) | (Product.description.like(f"%{q}%")))
    if category_id:
        query = query.filter_by(category_id=category_id)
    if brand_id:
        query = query.filter_by(brand_id=brand_id)
        
    if sort_by == 'price_asc':
        query = query.order_by(Product.offer_price.asc())
    elif sort_by == 'price_desc':
        query = query.order_by(Product.offer_price.desc())
    elif sort_by == 'newest':
        query = query.order_by(Product.created_at.desc())
        
    products = query.all()
    categories = Category.query.all()
    brands = Brand.query.all()
    
    # Find trending searches
    trending = db.session.query(SearchHistory.query, db.func.count(SearchHistory.id).label('qty'))\
        .group_by(SearchHistory.query)\
        .order_by(db.desc('qty'))\
        .limit(5).all()
    trending_queries = [t[0] for t in trending]
    
    return render_template(
        'main/search.html',
        products=products,
        query=q,
        categories=categories,
        brands=brands,
        selected_category=category_id,
        selected_brand=brand_id,
        sort_by=sort_by,
        trending_searches=trending_queries
    )

@main_bp.route('/submit-review/<int:product_id>', methods=['POST'])
def submit_review(product_id):
    if not current_user.is_authenticated:
        flash("You must be logged in to write a review.", "warning")
        return redirect(url_for('auth.login'))
        
    rating = request.form.get('rating', type=int)
    title = request.form.get('title', '').strip()
    content = request.form.get('content', '').strip()
    
    if not rating or not content:
        flash("Please provide a rating and review text.", "danger")
        return redirect(request.referrer)
        
    # Check if verified purchase (bought this product in a completed/delivered order)
    # Form lookup:
    from models import Order, OrderItem
    verified = db.session.query(OrderItem).join(Order).filter(
        Order.user_id == current_user.id,
        Order.status == 'Delivered',
        OrderItem.product_id == product_id
    ).first() is not None

    review = Review(
        user_id=current_user.id,
        product_id=product_id,
        rating=rating,
        title=title,
        content=content,
        is_verified_purchase=verified
    )
    db.session.add(review)
    db.session.commit()
    
    flash("Thank you for your review!", "success")
    return redirect(request.referrer)

@main_bp.route('/ask-question/<int:product_id>', methods=['POST'])
def ask_question(product_id):
    if not current_user.is_authenticated:
        flash("You must be logged in to ask questions.", "warning")
        return redirect(url_for('auth.login'))
        
    question_text = request.form.get('question', '').strip()
    if not question_text:
        flash("Question details cannot be empty.", "danger")
        return redirect(request.referrer)
        
    q = QuestionAnswer(
        product_id=product_id,
        user_id=current_user.id,
        question=question_text
    )
    db.session.add(q)
    db.session.commit()
    
    flash("Your question has been submitted successfully.", "success")
    return redirect(request.referrer)

@main_bp.route('/sellers')
def sellers_list():
    # Fetch all active, approved sellers
    sellers = StoreProfile.query.filter_by(status='Approved').all()
    return render_template('main/sellers.html', sellers=sellers)

@main_bp.route('/seller/<int:store_id>')
def seller_detail(store_id):
    # Fetch specific approved seller
    store = StoreProfile.query.filter_by(id=store_id, status='Approved').first_or_404()
    # Fetch active products for this seller
    products = Product.query.filter_by(seller_id=store.id, is_active=True).all()
    return render_template('main/seller_detail.html', store=store, products=products)

@main_bp.route('/privacy-policy')
def privacy_policy():
    return render_template('main/privacy.html')

@main_bp.route('/terms-conditions')
def terms_conditions():
    return render_template('main/terms.html')

@main_bp.route('/about-us')
def about_us():
    return render_template('main/about.html')

@main_bp.route('/careers')
def careers():
    return render_template('main/careers.html')

@main_bp.route('/press-releases')
def press_releases():
    return render_template('main/press.html')

@main_bp.route('/shipping-rates')
def shipping_rates():
    return render_template('main/shipping.html')

@main_bp.route('/returns-replacements')
def returns_replacements():
    return render_template('main/returns.html')


