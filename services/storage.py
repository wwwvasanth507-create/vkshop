import os
import io
import logging
from minio import Minio
from flask import current_app

logger = logging.getLogger('storage')

class StorageService:
    def __init__(self):
        self._client = None
        self._bucket_name = None

    @property
    def client(self):
        if self._client is None:
            endpoint = current_app.config.get('MINIO_ENDPOINT')
            access_key = current_app.config.get('MINIO_ACCESS_KEY')
            secret_key = current_app.config.get('MINIO_SECRET_KEY')
            secure = current_app.config.get('MINIO_SECURE', False)
            self._bucket_name = current_app.config.get('MINIO_BUCKET_NAME', 'ecom-uploads')
            
            if not all([endpoint, access_key, secret_key]):
                logger.warning("MinIO credentials not fully configured. S3 Storage Client disabled.")
                return None
                
            try:
                # Setup MinIO S3 client
                self._client = Minio(
                    endpoint,
                    access_key=access_key,
                    secret_key=secret_key,
                    secure=secure
                )
                # Ensure bucket exists
                if not self._client.bucket_exists(self._bucket_name):
                    self._client.make_bucket(self._bucket_name)
                    logger.info(f"Created MinIO S3 bucket: {self._bucket_name}")
            except Exception as e:
                logger.error(f"Failed to initialize MinIO client: {e}")
                self._client = None
        return self._client

    @property
    def bucket_name(self):
        # Trigger client resolution to populate bucket name
        self.client
        return self._bucket_name

    def upload_file_stream(self, stream, object_name, content_type=None):
        cli = self.client
        if cli is None:
            raise RuntimeError("MinIO client is not initialized.")
            
        # Get stream size safely
        stream.seek(0, io.SEEK_END)
        size = stream.tell()
        stream.seek(0)
        
        cli.put_object(
            self.bucket_name,
            object_name,
            stream,
            size,
            content_type=content_type or 'application/octet-stream'
        )
        logger.info(f"Uploaded {object_name} to MinIO S3 (Size: {size} bytes)")
        return object_name

    def get_file(self, object_name):
        cli = self.client
        if cli is None:
            raise RuntimeError("MinIO client is not initialized.")
        try:
            response = cli.get_object(self.bucket_name, object_name)
            stat = cli.stat_object(self.bucket_name, object_name)
            return response, stat
        except Exception as e:
            logger.error(f"Error fetching {object_name} from MinIO: {e}")
            raise

    def delete_file(self, object_name):
        cli = self.client
        if cli is None:
            return False
        try:
            cli.remove_object(self.bucket_name, object_name)
            logger.info(f"Deleted {object_name} from MinIO S3")
            return True
        except Exception as e:
            logger.error(f"Error deleting {object_name} from MinIO S3: {e}")
            return False

storage_service = StorageService()

def sync_local_uploads_to_minio():
    """
    Walk through local 'static/uploads' and upload files to MinIO.
    This guarantees that mock seeded files and previous uploads are copied over.
    """
    cli = storage_service.client
    if cli is None:
        logger.info("MinIO client not configured. Skipping uploads sync.")
        return
        
    uploads_dir = current_app.config.get('UPLOAD_FOLDER')
    if not uploads_dir or not os.path.exists(uploads_dir):
        logger.info("Local upload folder does not exist. Skipping sync.")
        return
        
    logger.info("Synchronizing local uploads folder to MinIO S3...")
    count = 0
    
    for root, _, files in os.walk(uploads_dir):
        for file in files:
            local_path = os.path.join(root, file)
            # Find relative path from static/uploads directory
            rel_path = os.path.relpath(local_path, uploads_dir)
            object_name = rel_path.replace('\\', '/')
            
            # Check if file exists in S3 bucket
            exists = False
            try:
                cli.stat_object(storage_service.bucket_name, object_name)
                exists = True
            except Exception:
                pass
                
            if not exists:
                try:
                    with open(local_path, 'rb') as f:
                        file_data = f.read()
                        size = len(file_data)
                        
                        import mimetypes
                        mime, _ = mimetypes.guess_type(local_path)
                        if mime is None:
                            mime = 'application/octet-stream'
                            
                        cli.put_object(
                            storage_service.bucket_name,
                            object_name,
                            io.BytesIO(file_data),
                            size,
                            content_type=mime
                        )
                        logger.info(f"[SYNC] Synced upload: {object_name}")
                        count += 1
                except Exception as e:
                    logger.error(f"[SYNC] Failed to sync {object_name}: {e}")
                    
    logger.info(f"Local uploads sync complete. Synced {count} file(s).")
