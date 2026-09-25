from apscheduler.schedulers.background import BackgroundScheduler
import os
import logging
from datetime import datetime, timedelta

# Set up logging for scheduler
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('scheduler')

scheduler = BackgroundScheduler()

import redis

_scheduler_lock_file = None

def get_redis_client():
    from flask import current_app
    redis_url = current_app.config.get('REDIS_URL')
    if redis_url:
        try:
            return redis.from_url(redis_url)
        except Exception:
            return None
    return None

def acquire_lock(client, lock_key, timeout=60):
    try:
        return client.set(lock_key, '1', ex=timeout, nx=True)
    except Exception:
        return False

def release_lock(client, lock_key):
    try:
        client.delete(lock_key)
    except Exception:
        pass

def auto_cancel_pending_orders_job(app):
    """
    Auto-cancel orders that have been in 'Pending' status for more than 3 days (72 hours).
    This catches UPI orders where the customer started checkout but never completed payment.
    Restores stock for cancelled orders.
    """
    with app.app_context():
        client = get_redis_client()
        if client:
            if not acquire_lock(client, "lock:auto_cancel_orders", timeout=90):
                return
        try:
            from models import Order, OrderItem, Product, ProductVariant, Notification
            from database import db
            from sqlalchemy.orm import joinedload

            cutoff_time = datetime.utcnow() - timedelta(days=3)

            # Find orders stuck in Pending for > 3 days (72h)
            pending_orders = Order.query.options(
                joinedload(Order.items).joinedload(OrderItem.variant),
                joinedload(Order.items).joinedload(OrderItem.product)
            ).filter(
                Order.status == 'Pending',
                Order.created_at < cutoff_time
            ).all()

            for order in pending_orders:
                # Restore stock for each item
                for item in order.items:
                    if item.variant_id and item.variant:
                        item.variant.stock += item.quantity
                    elif item.product_id and item.product:
                        item.product.stock += item.quantity

                order.status = 'Cancelled'
                db.session.add(order)

                # Notify the customer
                notif = Notification(
                    user_id=order.user_id,
                    title='Order Auto-Cancelled',
                    message=(
                        f'Your order {order.order_number} was automatically cancelled '
                        f'because payment was not completed within 3 days. '
                        f'If this was an error, please place a new order.'
                    ),
                    type='order'
                )
                db.session.add(notif)
                logger.info(f"Auto-cancelled order {order.order_number} (created at {order.created_at})")

            db.session.commit()
        finally:
            if client:
                release_lock(client, "lock:auto_cancel_orders")


def check_low_stock_job(app):
    """
    Check for products and variants with stock lower than or equal to 3.
    Creates notification alerts for relevant sellers.
    """
    with app.app_context():
        client = get_redis_client()
        if client:
            if not acquire_lock(client, "lock:check_low_stock", timeout=180):
                return
        try:
            from models import Product, ProductVariant, Notification, StoreProfile
            from database import db
            from sqlalchemy.orm import joinedload

            THRESHOLD = 3

            low_stock_products = Product.query.options(
                joinedload(Product.variants)
            ).filter(Product.is_active == True).all()
            for prod in low_stock_products:
                seller = StoreProfile.query.get(prod.seller_id)
                if not seller:
                    continue

                has_variants = len(prod.variants) > 0

                if has_variants:
                    # Check each variant
                    for var in prod.variants:
                        if var.stock <= THRESHOLD:
                            title = "Low Stock Alert"
                            msg = (
                                f"Your product '{prod.name}' "
                                f"(Variant: {' '.join(filter(None, [var.color, var.size, var.ram, var.storage]))} "
                                f"SKU: {var.sku}) has only {var.stock} piece(s) left!"
                            )
                            existing = Notification.query.filter_by(
                                user_id=seller.user_id,
                                title=title,
                                message=msg,
                                is_read=False
                            ).first()
                            if not existing:
                                notif = Notification(
                                    user_id=seller.user_id,
                                    title=title,
                                    message=msg,
                                    type='alert'
                                )
                                db.session.add(notif)
                                logger.info(
                                    f"Low stock notification for seller {seller.name}: "
                                    f"product '{prod.name}' variant {var.sku} has {var.stock} left"
                                )
                else:
                    # No variants — check base product stock
                    if prod.stock <= THRESHOLD:
                        title = "Low Stock Alert"
                        msg = f"Your product '{prod.name}' has only {prod.stock} piece(s) left!"
                        existing = Notification.query.filter_by(
                            user_id=seller.user_id,
                            title=title,
                            message=msg,
                            is_read=False
                        ).first()
                        if not existing:
                            notif = Notification(
                                user_id=seller.user_id,
                                title=title,
                                message=msg,
                                type='alert'
                            )
                            db.session.add(notif)
                            logger.info(
                                f"Low stock notification for seller {seller.name}: "
                                f"product '{prod.name}' has {prod.stock} left"
                            )

            db.session.commit()
        finally:
            if client:
                release_lock(client, "lock:check_low_stock")


def check_commission_suspension_job(app):
    """
    Check for sellers who have a pending commission payment request that is older than 3 days.
    If they haven't paid, change their commission_payment_status to 'Suspended'.
    """
    with app.app_context():
        client = get_redis_client()
        if client:
            if not acquire_lock(client, "lock:commission_suspension_check", timeout=180):
                return
        try:
            from models import StoreProfile
            from database import db

            limit_time = datetime.utcnow() - timedelta(days=3)
            overdue_stores = StoreProfile.query.filter(
                StoreProfile.commission_payment_status == 'Requested',
                StoreProfile.commission_requested_at < limit_time
            ).all()

            for store in overdue_stores:
                store.commission_payment_status = 'Suspended'
                db.session.add(store)
                logger.info(f"Suspended seller store '{store.name}' due to overdue commission payment.")

            db.session.commit()
        finally:
            if client:
                release_lock(client, "lock:commission_suspension_check")


def keep_alive_self_ping_job(app):
    """
    Self-ping the public /health endpoint every 10 minutes to prevent Render Free Tier from sleeping.
    Render edge proxy detects incoming HTTP requests to RENDER_EXTERNAL_URL / APP_URL and resets the 15-minute idle timeout.
    """
    import urllib.request
    target_url = (
        os.environ.get('APP_URL') or 
        os.environ.get('RENDER_EXTERNAL_URL') or 
        app.config.get('APP_URL')
    )
    if not target_url:
        return

    if not target_url.startswith(('http://', 'https://')):
        target_url = f"https://{target_url}"

    health_url = f"{target_url.rstrip('/')}/health"

    try:
        req = urllib.request.Request(
            health_url,
            headers={'User-Agent': 'VKShop-KeepAlive-Ping/1.0'}
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            if response.status == 200:
                logger.info(f"[KEEP-ALIVE] Ping to {health_url} succeeded (status 200). Render spin-down prevented.")
            else:
                logger.warning(f"[KEEP-ALIVE] Ping to {health_url} returned status: {response.status}")
    except Exception as e:
        logger.warning(f"[KEEP-ALIVE] Ping to {health_url} failed: {e}")


def init_scheduler(app):
    """
    Starts the background scheduler thread with the Flask application context.
    Safely prevents duplicate scheduler execution across multi-worker Gunicorn processes.
    """
    global _scheduler_lock_file

    if os.environ.get('DISABLE_SCHEDULER', 'False').lower() in ('true', '1', 't'):
        logger.info("Scheduler disabled via DISABLE_SCHEDULER environment variable.")
        return

    # Prevent duplicate runs in dev server reloader
    if not os.environ.get('WERKZEUG_RUN_MAIN') == 'true' and app.debug:
        logger.info("Skipping scheduler in main thread to wait for reloader...")
        return

    # Process lock check to ensure single scheduler instance across multi-worker Gunicorn
    try:
        lock_file_path = os.path.join(app.config.get('BASE_DIR', '.'), 'database', 'scheduler_active.pid')
        os.makedirs(os.path.dirname(lock_file_path), exist_ok=True)
        f = open(lock_file_path, 'a+')
        if os.name != 'nt':
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        else:
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        # Keep handle stored in global variable to prevent lock release on function exit
        _scheduler_lock_file = f
    except (ImportError, IOError, OSError, BlockingIOError) as e:
        logger.info(f"Scheduler already active in another worker process ({e}). Skipping duplicate startup.")
        return

    if not scheduler.running:
        # Auto-cancel pending orders every 2 minutes
        scheduler.add_job(
            func=auto_cancel_pending_orders_job,
            trigger="interval",
            minutes=2,
            args=[app],
            id="auto_cancel_orders"
        )
        # Low stock check every 10 minutes (threshold: 3 units)
        scheduler.add_job(
            func=check_low_stock_job,
            trigger="interval",
            minutes=10,
            args=[app],
            id="low_stock_check"
        )
        # Check commission suspension every 30 minutes
        scheduler.add_job(
            func=check_commission_suspension_job,
            trigger="interval",
            minutes=30,
            args=[app],
            id="commission_suspension_check"
        )
        # Keep-alive ping every 10 minutes to prevent Render Free Tier from sleeping (15-min idle timeout)
        scheduler.add_job(
            func=keep_alive_self_ping_job,
            trigger="interval",
            minutes=10,
            args=[app],
            id="keep_alive_self_ping"
        )
        scheduler.start()
        logger.info("APScheduler Background Job Thread Started successfully.")

