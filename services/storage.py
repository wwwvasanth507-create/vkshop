import os
import io
import uuid
import re
import logging
from typing import Tuple, Optional, Union
from minio import Minio
from flask import current_app
from PIL import Image, ImageOps

logger = logging.getLogger('storage')

# Set Pillow maximum pixel safety limit to defend against decompression bombs (25 Megapixels)
Image.MAX_IMAGE_PIXELS = 25 * 1024 * 1024

def sanitize_object_key(key: str) -> str:
    """
    Sanitize an object key/path to prevent path traversal attacks.
    Removes null bytes, backslashes, drive letters, leading slashes, and '../' sequences.
    """
    if not key:
        return f"uncategorized/{uuid.uuid4().hex}"
        
    # Remove null bytes
    s = key.replace('\x00', '')
    
    # Replace Windows backslashes with forward slashes
    s = s.replace('\\', '/')
    
    # Remove drive letters e.g. C:
    s = re.sub(r'^[a-zA-Z]:', '', s)
    
    # Remove path traversal tokens like ../ or ./
    parts = [p for p in s.split('/') if p and p not in ('.', '..')]
    
    clean_key = '/'.join(parts)
    return clean_key or f"uncategorized/{uuid.uuid4().hex}"

def generate_object_key(category: str, original_filename: str, extension: str = None) -> str:
    """
    Generate a safe, collision-resistant object key using a UUID.
    Example: products/b47f98d4-5390-48e0-a7bb-6a75f10adcfb.webp
    """
    cat = sanitize_object_key(category.strip().lower() if category else 'uploads')
    
    if extension:
        ext = extension.strip().lower()
        if not ext.startswith('.'):
            ext = f".{ext}"
    else:
        # Extract extension from original filename
        _, raw_ext = os.path.splitext(original_filename or '')
        ext = raw_ext.strip().lower()
        # Clean extension against non-alphanumeric chars
        ext = re.sub(r'[^a-z0-9\.]', '', ext)
        if not ext or len(ext) > 10:
            ext = '.webp'
            
    unique_id = uuid.uuid4().hex
    return f"{cat}/{unique_id}{ext}"

def optimize_image_bytes(
    image_input: Union[bytes, io.BytesIO],
    max_width: Optional[int] = None,
    max_height: Optional[int] = None,
    quality: Optional[int] = None,
    target_format: str = 'WEBP'
) -> Tuple[bytes, str, str]:
    """
    Validate and optimize an image using Pillow.
    - Validates image header and format (rejects corrupt images/decompression bombs/executable scripts/HTML/SVG).
    - Respects EXIF orientation.
    - Resizes image proportionally if dimensions exceed max_width/max_height (without upscaling).
    - Converts photographic images to WebP format by default with fast compression (method=0).
    - Preserves RGBA transparency if present.
    
    Returns:
        Tuple of (optimized_bytes, content_type, file_extension)
    """
    import time
    start_t = time.time()
    # Resolve configuration options
    try:
        max_w = max_width or current_app.config.get('IMAGE_MAX_WIDTH', 1200)
        max_h = max_height or current_app.config.get('IMAGE_MAX_HEIGHT', 1200)
        q = quality or current_app.config.get('IMAGE_WEBP_QUALITY', 80)
    except Exception:
        max_w = max_width or 1200
        max_h = max_height or 1200
        q = quality or 80

    # Read input into BytesIO buffer
    if isinstance(image_input, bytes):
        input_buf = io.BytesIO(image_input)
    else:
        image_input.seek(0)
        input_buf = io.BytesIO(image_input.read())
        image_input.seek(0)

    try:
        # Open image with Pillow to validate header and image structure
        with Image.open(input_buf) as img:
            # Check for invalid or unsafe formats
            if img.format in ('SVG', 'HTML', 'XBM'):
                raise ValueError(f"Unsupported or unsafe image format: {img.format}")

            # Verify image integrity
            img.verify()
            
            # Re-open after verify() as Pillow documentation specifies
            input_buf.seek(0)
            img = Image.open(input_buf)
            
            # Decompression bomb dimension check
            w, h = img.size
            if w * h > Image.MAX_IMAGE_PIXELS:
                raise ValueError(f"Image dimensions ({w}x{h}) exceed maximum pixel safety threshold.")

            # Correct EXIF orientation
            try:
                img = ImageOps.exif_transpose(img)
            except Exception as e:
                logger.debug(f"EXIF transpose skipped: {e}")

            # Calculate proportional resize (no upscaling)
            target_w, target_h = img.size
            if target_w > max_w or target_h > max_h:
                img.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)

            # Determine mode & save format
            fmt = target_format.upper()
            output_buf = io.BytesIO()

            if fmt == 'WEBP':
                if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                    img.save(output_buf, format='WEBP', quality=q, method=0)
                else:
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                    img.save(output_buf, format='WEBP', quality=q, method=0)
                content_type = 'image/webp'
                ext = '.webp'
            elif fmt in ('JPEG', 'JPG'):
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                img.save(output_buf, format='JPEG', quality=q, optimize=True)
                content_type = 'image/jpeg'
                ext = '.jpg'
            elif fmt == 'PNG':
                img.save(output_buf, format='PNG', optimize=True)
                content_type = 'image/png'
                ext = '.png'
            else:
                raise ValueError(f"Unsupported target format: {fmt}")

            duration_ms = int((time.time() - start_t) * 1000)
            res_bytes = output_buf.getvalue()
            logger.info(f"[IMAGE_OPTIMIZE] Processed in {duration_ms}ms ({w}x{h} -> {img.size[0]}x{img.size[1]}, Size: {len(res_bytes)} bytes)")
            return res_bytes, content_type, ext


    except Exception as e:
        logger.error(f"Image validation or optimization failed: {e}")
        raise ValueError(f"Invalid or corrupt image: {e}")

class StorageService:
    def __init__(self):
        self._client = None
        self._bucket_name = None

    def is_available(self) -> bool:
        """Return True if S3 client is configured and initialized."""
        return self.client is not None

    @property
    def client(self) -> Optional[Minio]:
        if self._client is None:
            try:
                endpoint = current_app.config.get('MINIO_ENDPOINT')
                access_key = current_app.config.get('MINIO_ACCESS_KEY')
                secret_key = current_app.config.get('MINIO_SECRET_KEY')
                secure = current_app.config.get('MINIO_SECURE', False)
                self._bucket_name = current_app.config.get('MINIO_BUCKET_NAME', 'ecom-uploads')
            except Exception:
                endpoint = os.environ.get('MINIO_ENDPOINT')
                access_key = os.environ.get('MINIO_ACCESS_KEY')
                secret_key = os.environ.get('MINIO_SECRET_KEY')
                secure = os.environ.get('MINIO_SECURE', 'False').lower() in ('true', '1', 't')
                self._bucket_name = os.environ.get('MINIO_BUCKET_NAME', 'ecom-uploads')

            if not all([endpoint, access_key, secret_key]):
                logger.warning("S3 credentials not fully configured. Object storage client disabled.")
                return None
                
            try:
                # Clean and normalize S3/R2 endpoint string
                clean_endpoint = str(endpoint).strip()
                if clean_endpoint.startswith(('http://', 'https://')):
                    secure = clean_endpoint.startswith('https://')
                    clean_endpoint = clean_endpoint.split('://', 1)[1]
                clean_endpoint = clean_endpoint.rstrip('/')

                # Setup MinIO S3 client (compatible with R2, S3, MinIO, Supabase)
                import urllib3
                http_client = urllib3.PoolManager(
                    timeout=urllib3.Timeout(connect=5.0, read=15.0),
                    maxsize=10,
                    retries=urllib3.Retry(total=2, backoff_factor=0.5)
                )
                self._client = Minio(
                    clean_endpoint,
                    access_key=access_key,
                    secret_key=secret_key,
                    secure=secure,
                    http_client=http_client
                )
                # Ensure bucket exists
                self.ensure_bucket()
            except Exception as e:
                logger.error(f"Failed to initialize S3 client: {e}")
                self._client = None
        return self._client

    @property
    def bucket_name(self) -> str:
        # Trigger client resolution to populate bucket name
        _ = self.client
        return self._bucket_name or 'ecom-uploads'

    def ensure_bucket(self) -> bool:
        """Ensure the configured bucket exists, creating it if permitted and missing."""
        if self._client is None:
            return False
        try:
            if not self._client.bucket_exists(self._bucket_name):
                self._client.make_bucket(self._bucket_name)
                logger.info(f"Created object storage bucket: {self._bucket_name}")
            return True
        except Exception as e:
            logger.warning(f"Could not verify or create bucket {self._bucket_name}: {e}")
            return True  # Return True if bucket creation failed due to permission restriction on existing bucket

    def upload_file_stream(self, stream, object_name: str, content_type: Optional[str] = None) -> str:
        """Upload a file stream to object storage with sanitized object key."""
        clean_key = sanitize_object_key(object_name)
        cli = self.client
        if cli is None:
            raise RuntimeError("Persistent storage client is not configured or initialized.")
            
        stream.seek(0, io.SEEK_END)
        size = stream.tell()
        stream.seek(0)
        
        cli.put_object(
            self.bucket_name,
            clean_key,
            stream,
            size,
            content_type=content_type or 'application/octet-stream'
        )
        logger.info(f"Uploaded {clean_key} to object storage (Size: {size} bytes)")
        return clean_key

    def upload_bytes(self, data: bytes, object_name: str, content_type: Optional[str] = None) -> str:
        """Upload a byte buffer directly to object storage."""
        buf = io.BytesIO(data)
        return self.upload_file_stream(buf, object_name, content_type=content_type)

    def get_file(self, object_name: str):
        """Retrieve object response stream and stat from storage."""
        clean_key = sanitize_object_key(object_name)
        cli = self.client
        if cli is None:
            raise RuntimeError("Persistent storage client is not configured or initialized.")
        try:
            response = cli.get_object(self.bucket_name, clean_key)
            stat = cli.stat_object(self.bucket_name, clean_key)
            return response, stat
        except Exception as e:
            logger.error(f"Error fetching {clean_key} from object storage: {e}")
            raise

    def file_exists(self, object_name: str) -> bool:
        """Check if object exists in storage bucket."""
        clean_key = sanitize_object_key(object_name)
        cli = self.client
        if cli is None:
            return False
        try:
            cli.stat_object(self.bucket_name, clean_key)
            return True
        except Exception:
            return False

    def delete_file(self, object_name: str) -> bool:
        """Safely delete object from storage bucket. Does not crash if object is missing."""
        clean_key = sanitize_object_key(object_name)
        cli = self.client
        if cli is None:
            return False
        try:
            cli.remove_object(self.bucket_name, clean_key)
            logger.info(f"Deleted {clean_key} from object storage")
            return True
        except Exception as e:
            logger.error(f"Error deleting {clean_key} from object storage: {e}")
            return False

    def get_public_url(self, object_name: str) -> str:
        """Return public CDN/storage URL or fallback route for an object key."""
        clean_key = sanitize_object_key(object_name)
        try:
            pub_base = current_app.config.get('STORAGE_PUBLIC_URL', '').rstrip('/')
        except Exception:
            pub_base = os.environ.get('STORAGE_PUBLIC_URL', '').rstrip('/')

        if pub_base:
            return f"{pub_base}/{clean_key}"
        return f"/static/uploads/{clean_key}"

storage_service = StorageService()

def normalize_storage_key(value: Optional[str]) -> Optional[str]:
    """
    Idempotently convert legacy filesystem paths, absolute paths, full R2 URLs, and wrapped keys
    into clean R2 object keys.
    Examples:
        https://pub-xxx.r2.dev/private/seller-documents/s1/a.webp -> private/seller-documents/s1/a.webp
        /static/uploads/users/private/seller-documents/seller1/a.webp -> private/seller-documents/seller1/a.webp
        static/uploads/products/a.webp -> products/a.webp
        users/private/seller-documents/seller1/a.webp -> private/seller-documents/seller1/a.webp
    """
    if not value:
        return None
    s = str(value).strip().replace('\\', '/')
    if not s:
        return None

    # Handle full HTTP/HTTPS URLs
    if s.startswith(('http://', 'https://')):
        pub_base = ""
        try:
            pub_base = current_app.config.get('STORAGE_PUBLIC_URL', '')
        except Exception:
            pub_base = os.environ.get('STORAGE_PUBLIC_URL', '')

        is_r2_domain = '.r2.dev' in s or (pub_base and pub_base in s)
        has_r2_key_prefix = any(p in s for p in ['/private/', '/products/', '/categories/', '/stores/', '/banners/', '/admin/', '/users/'])

        if is_r2_domain or has_r2_key_prefix:
            from urllib.parse import urlparse
            path = urlparse(s).path
            s = path.lstrip('/')
        else:
            return s  # Keep external non-R2 URLs as-is

    # Remove Windows drive letters e.g. C:
    s = re.sub(r'^[a-zA-Z]:', '', s)

    # Strip legacy local filesystem prefixes
    for prefix in ['/static/uploads/', 'static/uploads/', '/uploads/', 'uploads/', '/tmp/uploads/', 'tmp/uploads/']:
        if s.startswith(prefix):
            s = s[len(prefix):]
            break

    if s.startswith('users/private/'):
        s = s[len('users/'):]
    elif 'private/' in s and not s.startswith('private/'):
        idx = s.find('private/')
        s = s[idx:]

    parts = [p for p in s.split('/') if p and p not in ('.', '..')]
    return '/'.join(parts) if parts else None


def resolve_image_url(value: Optional[str], default_category: Optional[str] = None, private: bool = False) -> str:
    """
    Authoritative resolution of stored keys/paths to browser-accessible URLs.
    Supports public R2 URLs, authenticated private routes, complete HTTPS links, and fallback defaults.
    Ensures private objects NEVER leak as public R2 CDN links.
    """
    if not value:
        return '/static/uploads/placeholder.jpg'

    s = str(value).strip()
    if not s:
        return '/static/uploads/placeholder.jpg'

    key = normalize_storage_key(s)
    if not key:
        return '/static/uploads/placeholder.jpg'

    # If key is an external non-R2 HTTP(S) URL, return it
    if key.startswith(('http://', 'https://')):
        return key

    # Route ALL private documents through authenticated Flask endpoint
    if private or key.startswith('private/') or '/private/' in key:
        if not key.startswith('private/'):
            if 'private/' in key:
                key = key[key.find('private/'):]
            else:
                key = f"private/{key}"
        return f"/private/file/{key}"

    # Legacy filename reference e.g. img_1_foo.jpg without folder
    if '/' not in key:
        cat = (default_category or 'products').strip('/')
        key = f"{cat}/{key}"

    return storage_service.get_public_url(key)


def upload_file_field(file_obj, category: str, is_private: bool = False) -> Tuple[Optional[str], Optional[str]]:
    """
    Upload a Werkzeug FileStorage object using safe UUID object key & image optimization.
    Returns (object_key, error_message).
    """
    if not file_obj or not getattr(file_obj, 'filename', None):
        return None, None
        
    filename = file_obj.filename
    content_type = getattr(file_obj, 'content_type', '') or ''
    
    cat_prefix = f"private/{category}" if is_private else category
    
    file_obj.stream.seek(0)
    raw_data = file_obj.stream.read()
    file_obj.stream.seek(0)

    # Validate file size (10MB limit)
    MAX_FILE_SIZE = 10 * 1024 * 1024
    if len(raw_data) > MAX_FILE_SIZE:
        err_msg = f"File '{filename}' ({len(raw_data)} bytes) exceeds maximum size limit of 10MB."
        logger.warning(f"[UPLOAD] {err_msg}")
        return None, err_msg

    if len(raw_data) == 0:
        err_msg = f"Uploaded file '{filename}' is empty (0 bytes)."
        logger.warning(f"[UPLOAD] {err_msg}")
        return None, err_msg
    
    is_img = content_type.startswith('image/') or any(filename.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif'])
    
    ext = None
    upload_bytes_data = raw_data
    mime = content_type or 'application/octet-stream'
    
    if is_img:
        try:
            opt_bytes, opt_mime, opt_ext = optimize_image_bytes(raw_data)
            upload_bytes_data = opt_bytes
            mime = opt_mime
            ext = opt_ext
        except Exception as err:
            logger.warning(f"[UPLOAD] Image optimization skipped for {filename}: {err}")
            _, raw_ext = os.path.splitext(filename or '')
            ext = raw_ext.strip().lower() or '.bin'
    else:
        _, raw_ext = os.path.splitext(filename or '')
        ext = raw_ext.strip().lower() or '.bin'
            
    object_key = generate_object_key(cat_prefix, filename, extension=ext)
    
    if storage_service.is_available():
        try:
            storage_service.upload_bytes(upload_bytes_data, object_key, content_type=mime)
            logger.info(f"[UPLOAD SUCCESS] Key: {object_key}, Size: {len(upload_bytes_data)} bytes, MIME: {mime}")
            return object_key, None
        except Exception as e:
            logger.error(f"[UPLOAD ERROR] Failed to upload {object_key} to storage: {e}")
            return None, f"Failed to upload file to storage: {e}"
    else:
        try:
            allow_fallback = current_app.config.get('ALLOW_LOCAL_STORAGE_FALLBACK', True)
        except Exception:
            allow_fallback = True
            
        if not allow_fallback:
            err = f"Persistent object storage is unavailable and local fallback is disabled."
            logger.error(err)
            return None, err
            
        try:
            local_target = os.path.join(current_app.config['UPLOAD_FOLDER'], object_key.replace('/', os.sep))
            os.makedirs(os.path.dirname(local_target), exist_ok=True)
            with open(local_target, 'wb') as f:
                f.write(upload_bytes_data)
            logger.info(f"Local storage fallback saved: {object_key}")
            return object_key, None
        except Exception as e:
            return None, f"Failed to save upload locally: {e}"


def sync_local_uploads_to_minio():
    """
    Walk through local 'static/uploads' and upload files to object storage.
    Guarantees pre-existing local files are copied over to cloud bucket.
    """
    cli = storage_service.client
    if cli is None:
        logger.info("Object storage client not configured. Skipping uploads sync.")
        return
        
    try:
        uploads_dir = current_app.config.get('UPLOAD_FOLDER')
    except Exception:
        uploads_dir = None

    if not uploads_dir or not os.path.exists(uploads_dir):
        logger.info("Local upload folder does not exist. Skipping sync.")
        return
        
    logger.info("Synchronizing local uploads folder to object storage...")
    count = 0
    
    for root, _, files in os.walk(uploads_dir):
        for file in files:
            local_path = os.path.join(root, file)
            rel_path = os.path.relpath(local_path, uploads_dir)
            object_name = sanitize_object_key(rel_path)
            
            if not storage_service.file_exists(object_name):
                try:
                    with open(local_path, 'rb') as f:
                        file_data = f.read()
                        
                    import mimetypes
                    mime, _ = mimetypes.guess_type(local_path)
                    mime = mime or 'application/octet-stream'
                    
                    storage_service.upload_bytes(file_data, object_name, content_type=mime)
                    logger.info(f"[SYNC] Synced upload: {object_name}")
                    count += 1
                except Exception as e:
                    logger.error(f"[SYNC] Failed to sync {object_name}: {e}")
                    
    logger.info(f"Local uploads sync complete. Synced {count} file(s).")
