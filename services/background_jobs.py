import os
import logging
import concurrent.futures
import threading
from typing import Callable, Any, Dict

logger = logging.getLogger('background_jobs')

# High-concurrency thread pool fallback worker system
executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=int(os.environ.get('BACKGROUND_WORKERS', '4')),
    thread_name_prefix='vkshop_worker'
)

_job_lock = threading.Lock()
_job_status: Dict[str, str] = {}

def enqueue_job(fn: Callable, job_id: str = None, *args, **kwargs) -> Any:
    """
    Submit a task for asynchronous execution in the background pool.
    Returns Future object. Main API request returns immediately.
    Includes idempotency tracking using job_id if provided.
    """
    if job_id:
        with _job_lock:
            if _job_status.get(job_id) in ('RUNNING', 'COMPLETED'):
                logger.info(f"[JOB SKIPPED - ALREADY PROCESSED/RUNNING] JobID: {job_id}")
                return None
            _job_status[job_id] = 'RUNNING'

    def wrapped_fn():
        try:
            res = fn(*args, **kwargs)
            if job_id:
                with _job_lock:
                    _job_status[job_id] = 'COMPLETED'
            return res
        except Exception as err:
            logger.error(f"[JOB EXECUTION ERROR] JobID: {job_id or fn.__name__}, Error: {err}", exc_info=True)
            if job_id:
                with _job_lock:
                    _job_status[job_id] = 'FAILED'
            raise err

    try:
        future = executor.submit(wrapped_fn)
        logger.info(f"[JOB ENQUEUED] Function: {fn.__name__}, JobID: {job_id or 'auto'}")
        return future
    except Exception as e:
        logger.error(f"[JOB ENQUEUE FAIL] Function: {fn.__name__}, Error: {e}")
        # Synchronous fallback if background queue is saturated
        try:
            return wrapped_fn()
        except Exception as sync_err:
            logger.error(f"[SYNC FALLBACK FAIL] {sync_err}")
            return None

def process_image_optimization_async(file_bytes: bytes, object_key: str, content_type: str):
    """Background task to optimize uploaded image and generate thumbnail."""
    from services.storage import storage_service, optimize_image_bytes
    try:
        opt_bytes, opt_mime, _ = optimize_image_bytes(file_bytes)
        storage_service.upload_bytes(opt_bytes, object_key, content_type=opt_mime)
        # Also generate thumbnail in product-thumbnails/
        if object_key.startswith('products/'):
            storage_service.generate_thumbnail(opt_bytes, object_key)
        logger.info(f"[ASYNC IMAGE OPTIMIZED] Key: {object_key}")
    except Exception as e:
        logger.error(f"[ASYNC IMAGE OPTIMIZE FAIL] Key: {object_key}, Error: {e}")

def generate_invoice_pdf_async(order_id: int):
    """Background task to build order invoice PDF."""
    try:
        from services.invoice import InvoiceService
        pdf_bytes = InvoiceService.generate_invoice(order_id)
        if pdf_bytes:
            from services.storage import storage_service
            inv_key = f"invoices/order_{order_id}.pdf"
            storage_service.upload_bytes(pdf_bytes, inv_key, content_type='application/pdf')
            logger.info(f"[ASYNC INVOICE GENERATED] Key: {inv_key}")
    except Exception as e:
        logger.error(f"[ASYNC INVOICE FAIL] Order: {order_id}, Error: {e}")

