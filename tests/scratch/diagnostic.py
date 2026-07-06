
import os
import sys
import hashlib
import httpx
from datetime import datetime, timezone
import json

# Adjust path to import backend
sys.path.insert(0, os.path.abspath('backend'))

from app.db.session import SessionLocal
from app.models.fyers_token import FyersToken
from app.config import settings
from app.services.fyers_service import FyersService
from sqlalchemy import select, desc

def main():
    report = {}
    
    # Check env vars
    report['FYERS_PIN'] = 'SET' if settings.fyers_pin else 'MISSING'
    report['FYERS_CLIENT_ID'] = 'SET' if settings.fyers_app_id else 'MISSING'
    report['FYERS_SECRET_KEY'] = 'SET' if settings.fyers_secret_id else 'MISSING'
    
    app_id = settings.fyers_app_id or ''
    secret = settings.fyers_secret_id or ''
    app_id_hash = hashlib.sha256(f'{app_id}:{secret}'.encode()).hexdigest() if app_id and secret else 'Cannot compute (missing credentials)'
    report['appIdHash'] = app_id_hash
    
    db = SessionLocal()
    try:
        stmt = select(FyersToken).order_by(desc(FyersToken.created_at)).limit(3)
        rows = db.execute(stmt).scalars().all()
        
        if not rows:
            report['DB refresh token present'] = 'no (feature removed)'
            report['DB refresh token expired'] = 'N/A'
            report['FYERS API response status'] = 'N/A'
            report['FYERS API response body'] = 'N/A'
            print(json.dumps(report))
            return
            
        latest = rows[0]
        report['DB refresh token present'] = 'removed (access token only)'
        report['DB refresh token expired'] = 'N/A'
        report['FYERS API response status'] = 'N/A (refresh removed)'
        report['FYERS API response body'] = 'refresh/auto-renewal feature deleted'
            
    finally:
        db.close()
        
    for k, v in report.items():
        print(f'{k}: {v}')

if __name__ == '__main__':
    main()

