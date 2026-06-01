from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
response = client.get('/paper-trading/account')
print(response.status_code)
print(response.text)
