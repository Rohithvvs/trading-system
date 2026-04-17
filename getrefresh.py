from fyers_apiv3 import fyersModel

client_id = "V1WP4M0UME-100"
secret_key = "0SMFAZ3C7H"
redirect_uri = "https://trade.fyers.in/api-login/redirect-uri/index.html"
auth_code = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhcHBfaWQiOiJWMVdQNE0wVU1FIiwidXVpZCI6IjE1N2M5MWJjYTg2YzQ5ZDhhNTAwZWE4NmNlNzdjY2Q5IiwiaXBBZGRyIjoiIiwibm9uY2UiOiIiLCJzY29wZSI6IiIsImRpc3BsYXlfbmFtZSI6IllKMDg3MTgiLCJvbXMiOiJLMSIsImhzbV9rZXkiOiI4OWU3OGE2MWMzYTI0ZGYzODVkZGE4NDYyYzdlMjMxNTY3NDUwMzMwNjQ4Y2Q1M2M3NDYyZjJiMSIsImlzRGRwaUVuYWJsZWQiOiJOIiwiaXNNdGZFbmFibGVkIjoiTiIsImF1ZCI6IltcImQ6MVwiLFwiZDoyXCIsXCJ4OjBcIixcIng6MVwiXSIsImV4cCI6MTc3NTMzMDczOSwiaWF0IjoxNzc1MzAwNzM5LCJpc3MiOiJhcGkubG9naW4uZnllcnMuaW4iLCJuYmYiOjE3NzUzMDA3MzksInN1YiI6ImF1dGhfY29kZSJ9.oaY08g8bBKzzKXwMohNaXiZCKwBekn70b9a-wMb7nwQ"

session = fyersModel.SessionModel(
    client_id=client_id,
    secret_key=secret_key,
    redirect_uri=redirect_uri,
    response_type="code",
    grant_type="authorization_code"
)

session.set_token(auth_code)
response = session.generate_token()
print(response)
