from fyers_apiv3 import fyersModel
from urllib.parse import urlparse, parse_qs

CLIENT_ID = "V1WP4M0UME-100"
SECRET_KEY = "0SMFAZ3C7H"
REDIRECT_URI = "https://trade.fyers.in/api-login/redirect-uri/index.html"

session = fyersModel.SessionModel(
    client_id=CLIENT_ID,
    secret_key=SECRET_KEY,
    redirect_uri=REDIRECT_URI,
    response_type="code",
    grant_type="authorization_code"
)

auth_url = session.generate_authcode()

print("🔗 Click this URL NOW:")
print(auth_url)
print("\n⚡ Login → Copy auth code → Paste below (within 60 seconds!)")

user_input = input("\nPaste: ").strip()

# Extract auth code
if user_input.startswith('http'):
    auth_code = parse_qs(urlparse(user_input).query)['auth_code'][0]
else:
    auth_code = user_input

# Get token
session.set_token(auth_code)
response = session.generate_token()

if response.get('code') == 200:
    access_token = response["access_token"]
    print("\n✅ NEW TOKEN GENERATED!")
    print("=" * 60)
    print(f"Access Token:\n{access_token}")
    print("=" * 60)
    print("\n💾 COPY THIS TOKEN for the next cell!")

    # Store for next cell
    ACCESS_TOKEN = access_token
    print("\n✅ Token saved to variable ACCESS_TOKEN")
else:
    print(f"❌ Error: {response}")
