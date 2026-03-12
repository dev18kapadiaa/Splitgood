# Local Setup & Run Instructions (Expense Splitter)

1) Create Python venv and activate

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate
```

2) Install Python dependencies

```bash
pip install -r requirements.txt
```

3) Install PostgreSQL and create DB

```sql
-- in psql or pgAdmin
CREATE DATABASE expense_splitter;
-- ensure user credentials match .env (PGUSER / PGPASSWORD)
```

4) Install and run Redis

```bash
# macOS / Linux
redis-server
# Windows: use Redis for Windows or WSL
```

5) Create `.env` in project root (we added a template). Update secrets.

   - You may also supply an FX API key using `EXCHANGE_RATE_API_KEY`.  The
     default bundled key in settings is for development purposes and covers
     almost all worldwide currencies (AED, INR, etc.), but for production you
     should put your own key in `.env` or the environment.

6) Run migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

7) Build frontend (if using client/ with npm)

```bash
# from project root
cd client
npm install
npm run build
cd ..
python manage.py collectstatic --noinput
```

8) Start services

Terminal 1: Django
```bash
python manage.py runserver
```

Terminal 2: Celery worker
```bash
# from project root
celery -A splitgood worker --loglevel=info
```

Terminal 3 (optional): Celery beat
```bash
celery -A splitgood beat --loglevel=info
```

9) Notes
- For email testing, leaving `EMAIL_HOST_USER` empty will use console email backend.
- If you prefer `DATABASE_URL`, set it in `.env` and it will be used by settings.
- On Windows, activate venv with `venv\Scripts\activate`.

10) Google OAuth redirect URI (required)

 - In Google Cloud Console > Credentials > OAuth 2.0 Client IDs, edit your client and add the following Authorized redirect URIs:
	 - `http://127.0.0.1:8000/accounts/google/login/callback/`
	 - `http://localhost:8000/accounts/google/login/callback/`

 - Ensure your `.env` contains `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` and optionally `SITE_DOMAIN` (defaults to `127.0.0.1:8000`). The management command `configure_oauth` will create the `SocialApp` and link it to local Site entries automatically on `runserver`.

11) Alternative: manually create SocialApp

 - You can also create the SocialApp in Django admin (/admin/) under "Social applications" and attach it to the Site(s) `127.0.0.1:8000` and `localhost:8000`.
