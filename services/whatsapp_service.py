import logging
import json
from datetime import datetime, timedelta
from database import db
from models import WhatsAppMessage, WhatsAppMessageStatus, WhatsAppMessageAudit, AdminNotification, Order, User, Role

logger = logging.getLogger('whatsapp_service')

def create_whatsapp_message_for_order(order_or_id):
    """
    Generate persistent WhatsApp message for a newly created order.
    Idempotent: Uses order_id unique constraint to prevent duplicates if order creation is retried.
    Accepts either an Order instance or an integer order_id.
    """
    if not order_or_id:
        return None

    if isinstance(order_or_id, (int, str)):
        order = Order.query.get(int(order_or_id))
    else:
        order = order_or_id

    if not order:
        return None

    # Check existing message for idempotency
    existing = WhatsAppMessage.query.filter_by(order_id=order.id).first()
    if existing:
        logger.info(f"[WHATSAPP] WhatsApp message for Order #{order.order_number} already exists (id={existing.id}). Skipped duplicate.")
        return existing

    # Customer phone number resolution (order address contact or user phone)
    phone = ""
    if order.address and getattr(order.address, 'contact_number', None):
        phone = order.address.contact_number
    elif hasattr(order.user, 'contact_number') and order.user.contact_number:
        phone = order.user.contact_number
    elif hasattr(order.user, 'username') and order.user.username.isdigit():
        phone = order.user.username
    else:
        phone = "919876543210" # Default fallback placeholder if no customer phone found

    customer_name = order.address.fullName if (order.address and order.address.fullName) else order.user.username

    # Format order items list
    item_lines = []
    if order.items:
        for item in order.items:
            name = item.product_name or (item.product.name if item.product else 'Product')
            item_lines.append(f"{item.quantity} × {name}")
    items_str = "\n".join(item_lines) if item_lines else "Order Items"

    message_text = (
        f"🛍️ VKShop New Order\n\n"
        f"Order: #{order.order_number}\n"
        f"Customer: {customer_name}\n"
        f"Total: ₹{order.grand_total:,.2f}\n\n"
        f"Items:\n{items_str}\n\n"
        f"Please review the order in VKShop Admin."
    )

    msg = WhatsAppMessage(
        order_id=order.id,
        customer_id=order.user_id,
        customer_phone=phone,
        message_text=message_text,
        status=WhatsAppMessageStatus.PENDING,
        version=1
    )
    db.session.add(msg)
    db.session.flush() # Obtains msg.id

    # Create audit log
    audit = WhatsAppMessageAudit(
        message_id=msg.id,
        admin_id=None,
        action='CREATED',
        metadata_json=json.dumps({'order_number': order.order_number, 'grand_total': order.grand_total})
    )
    db.session.add(audit)

    # Create AdminNotification record for header bell
    notif = AdminNotification(
        admin_id=None, # Broadcast to all admins
        type='whatsapp_created',
        title=f"New Order #{order.order_number}",
        body=f"Order #{order.order_number} received (₹{order.grand_total:,.2f}). Pending WhatsApp send.",
        reference_type='whatsapp',
        reference_id=msg.id
    )
    db.session.add(notif)
    db.session.commit()

    logger.info(f"[WHATSAPP] Created WhatsApp message #{msg.id} for Order #{order.order_number}")

    # Broadcast Live SSE Event to all connected admins
    from services.sse_service import publish_admin_event
    publish_admin_event('whatsapp_created', {
        'message_id': msg.id,
        'order_id': order.id,
        'order_number': order.order_number,
        'customer_name': customer_name,
        'customer_phone': msg.customer_phone,
        'grand_total': order.grand_total,
        'status': msg.status,
        'created_at': msg.created_at.isoformat()
    })
    publish_admin_event('notification_created', {
        'id': notif.id,
        'title': notif.title,
        'body': notif.body,
        'reference_id': msg.id
    })

    # Broadcast FCM Push Notification asynchronously to active admin devices
    from services.firebase_service import broadcast_admin_fcm_notification
    broadcast_admin_fcm_notification(
        title=f"New Order #{order.order_number}",
        body=f"₹{order.grand_total:,.2f} - {customer_name}",
        data={'type': 'new_order', 'order_id': str(order.id), 'whatsapp_message_id': str(msg.id)}
    )

    return msg


def claim_whatsapp_message(message_id, admin_id, expected_version=None):
    """
    Atomic PostgreSQL claim of a WhatsApp message (PENDING -> SENDING).
    Optimistic concurrency control: checks status == 'PENDING' and version == expected_version.
    Prevents multiple admins from claiming the same message concurrently.
    """
    msg = WhatsAppMessage.query.get(message_id)
    if not msg:
        return {'success': False, 'reason': 'not_found', 'message': 'WhatsApp message not found.'}

    if msg.status != WhatsAppMessageStatus.PENDING:
        return {'success': False, 'reason': 'already_claimed', 'message': f'Message is already in status {msg.status}.'}

    target_version = expected_version if expected_version is not None else msg.version

    # Atomic SQL Update
    affected = db.session.query(WhatsAppMessage).filter(
        WhatsAppMessage.id == message_id,
        WhatsAppMessage.status == WhatsAppMessageStatus.PENDING,
        WhatsAppMessage.version == target_version
    ).update({
        WhatsAppMessage.status: WhatsAppMessageStatus.SENDING,
        WhatsAppMessage.sent_by_admin_id: admin_id,
        WhatsAppMessage.updated_at: datetime.utcnow(),
        WhatsAppMessage.version: WhatsAppMessage.version + 1
    }, synchronize_session=False)

    if affected == 0:
        db.session.rollback()
        return {'success': False, 'reason': 'already_claimed', 'message': 'Message was claimed by another admin.'}

    db.session.commit()

    # Re-query updated message
    msg = WhatsAppMessage.query.get(message_id)
    admin_user = User.query.get(admin_id)
    admin_name = admin_user.username if admin_user else f"Admin #{admin_id}"

    # Audit log
    audit = WhatsAppMessageAudit(
        message_id=msg.id,
        admin_id=admin_id,
        action='SEND_STARTED',
        metadata_json=json.dumps({'admin_name': admin_name, 'version': msg.version})
    )
    db.session.add(audit)
    db.session.commit()

    logger.info(f"[WHATSAPP] Message #{message_id} claimed by {admin_name}")

    # Broadcast Live SSE Event
    from services.sse_service import publish_admin_event
    publish_admin_event('whatsapp_claimed', {
        'message_id': msg.id,
        'order_id': msg.order_id,
        'admin_id': admin_id,
        'admin_name': admin_name,
        'status': msg.status,
        'version': msg.version,
        'deep_link': msg.whatsapp_deep_link
    })

    return {
        'success': True,
        'message_id': msg.id,
        'message': msg,
        'status': msg.status,
        'deep_link': msg.whatsapp_deep_link,
        'version': msg.version
    }


def confirm_whatsapp_message_sent(message_id, admin_id, is_sent=True):
    """
    Two-Phase confirmation flow:
    - If is_sent == True: Transition SENDING -> SENT. Sets sent_at timestamp.
    - If is_sent == False: Transition SENDING -> PENDING. Releases message back to queue.
    """
    msg = WhatsAppMessage.query.get(message_id)
    if not msg:
        return {'success': False, 'reason': 'not_found', 'message': 'WhatsApp message not found.'}

    if msg.status != WhatsAppMessageStatus.SENDING:
        return {'success': False, 'reason': 'invalid_state', 'message': f'Message is in state {msg.status}, not SENDING.'}

    if msg.sent_by_admin_id and msg.sent_by_admin_id != admin_id:
        return {'success': False, 'reason': 'not_claimed_by_you', 'message': f'Message was claimed by Admin #{msg.sent_by_admin_id}.'}

    admin_user = User.query.get(admin_id)
    admin_name = admin_user.username if admin_user else f"Admin #{admin_id}"

    if is_sent:
        msg.status = WhatsAppMessageStatus.SENT
        msg.sent_at = datetime.utcnow()
        msg.version += 1
        msg.updated_at = datetime.utcnow()

        audit = WhatsAppMessageAudit(
            message_id=msg.id,
            admin_id=admin_id,
            action='SEND_CONFIRMED',
            metadata_json=json.dumps({'sent_at': msg.sent_at.isoformat(), 'admin_name': admin_name})
        )
        db.session.add(audit)
        db.session.commit()

        logger.info(f"[WHATSAPP] Message #{message_id} confirmed SENT by {admin_name}")

        from services.sse_service import publish_admin_event
        publish_admin_event('whatsapp_sent', {
            'message_id': msg.id,
            'order_id': msg.order_id,
            'admin_id': admin_id,
            'admin_name': admin_name,
            'status': msg.status,
            'sent_at': msg.sent_at.isoformat()
        })
    else:
        # User reported message was not sent -> Revert SENDING -> PENDING
        msg.status = WhatsAppMessageStatus.PENDING
        msg.sent_by_admin_id = None
        msg.version += 1
        msg.updated_at = datetime.utcnow()

        audit = WhatsAppMessageAudit(
            message_id=msg.id,
            admin_id=admin_id,
            action='SEND_FAILED',
            metadata_json=json.dumps({'reason': 'user_released_to_pending', 'admin_name': admin_name})
        )
        db.session.add(audit)
        db.session.commit()

        logger.info(f"[WHATSAPP] Message #{message_id} released back to PENDING by {admin_name}")

        from services.sse_service import publish_admin_event
        publish_admin_event('whatsapp_released', {
            'message_id': msg.id,
            'order_id': msg.order_id,
            'status': msg.status,
            'reason': 'user_released'
        })

    return {'success': True, 'status': msg.status, 'message': msg, 'message_id': msg.id}


def recover_stale_sending_messages(app=None, timeout_seconds=300):
    """
    Stale SENDING recovery job.
    Reverts WhatsAppMessage records stuck in SENDING status for > timeout_seconds back to PENDING.
    """
    if app:
        with app.app_context():
            return _execute_stale_recovery(timeout_seconds)
    else:
        return _execute_stale_recovery(timeout_seconds)

def _execute_stale_recovery(timeout_seconds=300):
    try:
        cutoff = datetime.utcnow() - timedelta(seconds=timeout_seconds)
        stale_messages = WhatsAppMessage.query.filter(
            WhatsAppMessage.status == WhatsAppMessageStatus.SENDING,
            WhatsAppMessage.updated_at < cutoff
        ).all()

        if not stale_messages:
            return 0

        for msg in stale_messages:
            old_admin_id = msg.sent_by_admin_id
            msg.status = WhatsAppMessageStatus.PENDING
            msg.sent_by_admin_id = None
            msg.version += 1
            msg.updated_at = datetime.utcnow()

            audit = WhatsAppMessageAudit(
                message_id=msg.id,
                admin_id=old_admin_id,
                action='SEND_FAILED',
                metadata_json=json.dumps({'reason': 'stale_timeout_recovery', 'cutoff': cutoff.isoformat()})
            )
            db.session.add(audit)

        db.session.commit()
        logger.info(f"[WHATSAPP-RECOVERY] Recovered {len(stale_messages)} stale SENDING messages back to PENDING.")

        from services.sse_service import publish_admin_event
        for msg in stale_messages:
            publish_admin_event('whatsapp_released', {
                'message_id': msg.id,
                'order_id': msg.order_id,
                'status': msg.status,
                'reason': 'stale_timeout'
            })
        return len(stale_messages)
    except Exception as err:
        logger.error(f"[WHATSAPP-RECOVERY] Error recovering stale sending messages: {err}")
        db.session.rollback()
        return 0
