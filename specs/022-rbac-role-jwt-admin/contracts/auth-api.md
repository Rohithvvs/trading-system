# API Contracts: Authentication & Role Domain

## Endpoint 1: User Registration
* **HTTP Method**: `POST`
* **Path**: `/auth/register`
* **Auth Required**: No (Public)

### Request Body
```json
{
  "email": "user@example.com",
  "password": "SecurePassword123!",
  "full_name": "Jane Doe"
}
```

### Response (HTTP 201 Created)
```json
{
  "id": "usr_98765",
  "email": "user@example.com",
  "full_name": "Jane Doe",
  "role": "trader",
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

---

## Endpoint 2: User Login
* **HTTP Method**: `POST`
* **Path**: `/auth/login`
* **Auth Required**: No (Public)

### Request Body
```json
{
  "email": "user@example.com",
  "password": "SecurePassword123!"
}
```

### Response (HTTP 200 OK)
```json
{
  "id": "usr_98765",
  "email": "user@example.com",
  "full_name": "Jane Doe",
  "role": "trader",
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

---

## Endpoint 3: Profile & Session Verification
* **HTTP Method**: `GET`
* **Path**: `/auth/me`
* **Auth Required**: Yes (`Authorization: Bearer <access_token>`)

### Response (HTTP 200 OK)
```json
{
  "id": "usr_98765",
  "email": "user@example.com",
  "full_name": "Jane Doe",
  "role": "trader"
}
```

---

## Standard Error Response Schemas

### HTTP 401 Unauthorized
```json
{
  "error": "Unauthorized",
  "message": "Invalid email or password"
}
```

### HTTP 400 Bad Request / 422 Unprocessable Entity
```json
{
  "error": "Bad Request",
  "message": "Email address already registered"
}
```
