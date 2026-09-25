import os
from app import app
from waitress import serve

if __name__ == '__main__':
    # Enforce environment settings for production safety
    os.environ['FLASK_ENV'] = 'production'
    os.environ['FLASK_DEBUG'] = 'False'
    
    # Auto-initialize and seed DB if empty
    with app.app_context():
        from models import User
        if User.query.count() == 0:
            print("Production database is empty. Launching auto-seeder...")
            from seed import seed_database
            seed_database()
        
    port = int(os.environ.get('PORT', 5000))
    print(f"Launching ultra-fast multi-threaded Waitress WSGI Server on http://0.0.0.0:{port}")
    serve(app, host='0.0.0.0', port=port, threads=64, connection_limit=2000, channel_timeout=15, recv_bytes=65536, send_bytes=65536)
