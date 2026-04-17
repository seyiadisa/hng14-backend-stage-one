# Name Profile Classification API

A FastAPI service that accepts a person's name, calls three public inference APIs, classifies the result, stores it in a SQLite database, and exposes endpoints to create, list, fetch, and delete profiles.

This project was built for the HNG Stage One backend task.

## Features

- Creates a profile from a single `name` input.
- Calls these external APIs:
  - `https://api.genderize.io?name={name}`
  - `https://api.agify.io?name={name}`
  - `https://api.nationalize.io?name={name}`
- Derives:
  - `gender` and `gender_probability` from Genderize
  - `age` from Agify
  - `age_group` using the required classification rules
  - `country_id` and `country_probability` from the highest-probability Nationalize result
- Stores profiles in SQLite using SQLAlchemy async.
- Prevents duplicate profile creation for the same name.
- Supports filtering on the list endpoint.
- Returns UTC ISO 8601 timestamps.
- Uses UUID v7 for profile IDs.

## Classification Rules

- `0-12` -> `child`
- `13-19` -> `teenager`
- `20-59` -> `adult`
- `60+` -> `senior`

For nationality, the API selects the country with the highest probability from the Nationalize response.

## Tech Stack

- Python `3.14+`
- FastAPI
- SQLAlchemy Async ORM
- SQLite with `aiosqlite`

## Project Structure

```text
.
|-- main.py
|-- routes.py
|-- models.py
|-- schemas.py
|-- db.py
|-- config.py
|-- utils.py
|-- profiles.db
|-- pyproject.toml
`-- .env
```

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/seyiadisa/hng14-backend-stage-one.git stage-one
cd stage-one
```

### 2. Create and activate a virtual environment

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

If you use `uv`:

```bash
uv sync
```

If you use `pip`:

```bash
pip install "fastapi[standard]" sqlalchemy aiosqlite
```

### 4. Configure environment variables

Create a `.env` file in the project root:

```env
DATABASE_URL=sqlite+aiosqlite:///./profiles.db
```

## Running the Application

Start the development server with:

```bash
fastapi dev main.py
```

Or with Uvicorn:

```bash
uvicorn main:app --reload
```

The API will be available at:

- `http://127.0.0.1:8000`

Interactive docs:

- `http://127.0.0.1:8000/docs`

## API Endpoints


### 1. Create Profile

`POST /api/profiles`

Request body:

```json
{
  "name": "ella"
}
```

Success response:

```json
{
  "status": "success",
  "data": {
    "id": "01964365-89e8-7f6f-a72e-837b5b668b73",
    "name": "ella",
    "gender": "female",
    "gender_probability": 0.99,
    "sample_size": 1234,
    "age": 46,
    "age_group": "adult",
    "country_id": "DR",
    "country_probability": 0.85,
    "created_at": "2026-04-17T21:00:00Z"
  }
}
```

If the same name already exists:

```json
{
  "status": "success",
  "message": "Profile already exists",
  "data": {
    "id": "01964365-89e8-7f6f-a72e-837b5b668b73",
    "name": "ella",
    "gender": "female",
    "gender_probability": 0.99,
    "sample_size": 1234,
    "age": 46,
    "age_group": "adult",
    "country_id": "DR",
    "country_probability": 0.85,
    "created_at": "2026-04-17T21:00:00Z"
  }
}
```

### 2. Get Single Profile

`GET /api/profiles/{id}`

Success response:

```json
{
  "status": "success",
  "data": {
    "id": "01964365-89e8-7f6f-a72e-837b5b668b73",
    "name": "emmanuel",
    "gender": "male",
    "gender_probability": 0.99,
    "sample_size": 1234,
    "age": 25,
    "age_group": "adult",
    "country_id": "NG",
    "country_probability": 0.85,
    "created_at": "2026-04-17T21:00:00Z"
  }
}
```

### 3. Get All Profiles

`GET /api/profiles`

Optional query parameters:

- `gender`
- `country_id`
- `age_group`

These filters are case-insensitive.

Example:

```text
/api/profiles?gender=male&country_id=NG
```

Success response:

```json
{
  "status": "success",
  "count": 2,
  "data": [
    {
      "id": "01964365-89e8-7f6f-a72e-837b5b668b73",
      "name": "emmanuel",
      "gender": "male",
      "age": 25,
      "age_group": "adult",
      "country_id": "NG"
    },
    {
      "id": "01964366-29b2-73de-96d0-a05b80f0f1ce",
      "name": "sarah",
      "gender": "female",
      "age": 28,
      "age_group": "adult",
      "country_id": "US"
    }
  ]
}
```

### 4. Delete Profile

`DELETE /api/profiles/{id}`

Success response:

- `204 No Content`

## Error Responses

All errors follow this structure:

```json
{
  "status": "error",
  "message": "<error message>"
}
```

Possible errors:

- `400 Bad Request` -> `Missing or empty name`
- `404 Not Found` -> `Profile not found`
- `422 Unprocessable Entity` -> `Invalid type`
- `500 Internal Server Error` -> `Internal server error`
- `502 Bad Gateway` -> `${externalApi} returned an invalid response`

Examples:

```json
{
  "status": "error",
  "message": "Missing or empty name"
}
```

```json
{
  "status": "error",
  "message": "Genderize returned an invalid response"
}
```

## External API Validation Rules

The service does not store a profile when any upstream API returns invalid data.

- Genderize must return:
  - non-null `gender`
  - non-zero `count`
- Agify must return:
  - non-null `age`
- Nationalize must return:
  - at least one country entry

If any of these validations fail, the API responds with `502 Bad Gateway`.

## Persistence

- Profiles are stored in a local SQLite database.
- The default database file is `profiles.db`.
- Tables are created automatically when the app starts.

## CORS

The API is configured with:

```text
Access-Control-Allow-Origin: *
```

This is required so external grading scripts can access the API.

## Example cURL Requests

Create a profile:

```bash
curl -X POST "http://127.0.0.1:8000/api/profiles" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"ella\"}"
```

Get all profiles:

```bash
curl "http://127.0.0.1:8000/api/profiles"
```

Filter profiles:

```bash
curl "http://127.0.0.1:8000/api/profiles?gender=female&country_id=US&age_group=adult"
```

Get one profile:

```bash
curl "http://127.0.0.1:8000/api/profiles/<profile-id>"
```

Delete a profile:

```bash
curl -X DELETE "http://127.0.0.1:8000/api/profiles/<profile-id>"
```

## Notes

- Names are normalized before storage to support idempotent profile creation.
- Timestamps are serialized in UTC with the `Z` suffix.
- IDs are generated as UUID v7 values.
- The list endpoint intentionally returns a smaller payload than the single-profile endpoint.

## Author

Built by Oluwaseyi Adisa.
