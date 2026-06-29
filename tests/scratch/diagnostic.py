
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
            report['DB refresh token present'] = 'no'
            report['DB refresh token expired'] = 'N/A'
            report['FYERS API response status'] = 'N/A'
            report['FYERS API response body'] = 'N/A'
            print(json.dumps(report))
            return
            
        latest = rows[0]
        has_refresh = latest.refresh_token is not None
        report['DB refresh token present'] = 'yes' if has_refresh else 'no'
        
        if has_refresh and latest.refresh_token_expires_at:
            # check if expired
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            is_expired = latest.refresh_token_expires_at < now
            report['DB refresh token expired'] = 'yes' if is_expired else 'no'
        else:
            report['DB refresh token expired'] = 'N/A'
            
        if has_refresh:
            service = FyersService()
            raw_refresh = service.decrypt_token(latest.refresh_token)
            
            payload = {
                'grant_type': 'refresh_token',
                'appIdHash': app_id_hash,
                'refresh_token': raw_refresh,
                'pin': settings.fyers_pin or ''
            }
            
            try:
                response = httpx.post('https://api-t1.fyers.in/api/v3/validate-refresh-token', json=payload, timeout=30.0)
                report['FYERS API response status'] = response.status_code
                
                try:
                    data = response.json()
                    if 'access_token' in data:
                        data['access_token'] = str(data['access_token'])[:10] + '***'
                    report['FYERS API response body'] = json.dumps(data)
                except Exception as e:
                    report['FYERS API response body'] = response.text
            except Exception as e:
                report['FYERS API response status'] = 'ERROR'
                report['FYERS API response body'] = str(e)
        else:
            report['FYERS API response status'] = 'N/A (No refresh token)'
            report['FYERS API response body'] = 'N/A (No refresh token)'
            
    finally:
        db.close()
        
    for k, v in report.items():
        print(f'{k}: {v}')

if __name__ == '__main__':
    main()

