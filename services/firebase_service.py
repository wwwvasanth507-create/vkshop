import os
import json
import logging
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger('firebase_service')

_firebase_initialized = False
_executor = ThreadPoolExecutor(max_workers=4)

def _init_firebase_app():
    global _firebase_initialized
    if _firebase_initialized:
        return True

    cred_json_str = os.environ.get('FIREBASE_CREDENTIALS_JSON', '').strip()
    if not cred_json_str:
        logger.info("[FCM] FIREBASE_CREDENTIALS_JSON is not configured. FCM push notifications disabled.")
        return False

    try:
        import firebase_admin
        from firebase_admin import credentials

        if not firebase_admin._apps:
            cred_dict = json.loads(cred_json_str)
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
            logger.info("[FCM] Firebase Admin SDK successfully initialized.")
        _firebase_initialized = True
        return True
    except Exception as e:
        logger.error(f"[FCM] Failed to initialize Firebase Admin SDK: {e}")
        return False


def send_fcm_notification_to_tokens(tokens, title, body, data=None):
    """
    Sends FCM notification to a list of device tokens.
    Executes in background thread pool to avoid blocking HTTP requests.
    """
    if not tokens:
        return

    def _async_send():
        try:
            if not _init_firebase_app():
                return

            from firebase_admin import messaging

            # Filter non-empty valid tokens
            valid_tokens = [t for t in tokens if t and isinstance(t, str)]
            if not valid_tokens:
                return

            str_data = {str(k): str(v) for k, v in (data or {}).items()}

            message = messaging.MulticastMessage(
                notification=messaging.Notification(
                    title=title,
                    body=body
                ),
                data=str_data,
                tokens=valid_tokens
            )
            response = messaging.send_multicast(message)
            logger.info(f"[FCM] Sent notification '{title}' to {response.success_count}/{len(valid_tokens)} devices.")
        except Exception as err:
            logger.error(f"[FCM] Error sending multicast notification: {err}")

    _executor.submit(_async_send)


def send_admin_fcm_notification(admin_id, title, body, data=None):
    """Send FCM notification to all active registered devices of a specific admin."""
    from models import AdminDevice
    try:
        devices = AdminDevice.query.filter_by(admin_id=admin_id, is_active=True).all()
        tokens = [d.fcm_token for d in devices if d.fcm_token]
        if tokens:
            send_fcm_notification_to_tokens(tokens, title, body, data)
    except Exception as err:
        logger.error(f"[FCM] Failed to query admin devices for admin_id={admin_id}: {err}")


def send_admin_notification(admin_id, title, body, data=None, notification_type='general', reference_type=None, reference_id=None):
    """
    Helper function required by spec:
    Creates persistent AdminNotification database record and dispatches FCM notification.
    """
    from database import db
    from models import AdminNotification
    try:
        ref_id = None
        if reference_id is not None:
            try:
                ref_id = int(reference_id)
            except ValueError:
                ref_id = None

        notif = AdminNotification(
            admin_id=admin_id,
            type=notification_type,
            title=title,
            body=body,
            reference_type=reference_type,
            reference_id=ref_id
        )
        db.session.add(notif)
        db.session.commit()

        # Send FCM push if admin_id provided or broadcast if admin_id is None
        if admin_id:
            send_admin_fcm_notification(admin_id, title, body, data)
        else:
            broadcast_admin_fcm_notification(title, body, data)

        return notif
    except Exception as err:
        logger.error(f"[FCM] Failed to create admin notification: {err}")
        db.session.rollback()
        return None


def broadcast_admin_fcm_notification(title, body, data=None):
    """Broadcast FCM notification to all active registered devices of all active admins."""
    from models import AdminDevice, User, Role
    try:
        devices = AdminDevice.query.join(User).filter(
            User.role.in_([Role.ADMIN, Role.SUB_ADMIN]),
            User.is_active == True,
            AdminDevice.is_active == True
        ).all()
        tokens = list(set([d.fcm_token for d in devices if d.fcm_token]))
        if tokens:
            send_fcm_notification_to_tokens(tokens, title, body, data)
    except Exception as err:
        logger.error(f"[FCM] Failed to query broadcast admin devices: {err}")

