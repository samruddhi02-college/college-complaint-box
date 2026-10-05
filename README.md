# College Complaint Box — Cloud Deployment

A Flask-based College Complaint Box with student registration/login, complaint submission, tracking, and an admin dashboard.

## Run locally

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
# source venv/bin/activate

pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000`.

## Deploy on Render

1. Upload this project to a GitHub repository.
2. In Render, create a new **Blueprint** from the repository. Render will read `render.yaml`.
3. When prompted, enter values for:
   - `ADMIN_USERNAME`
   - `ADMIN_PASSWORD`
4. Deploy the service.
5. Open the generated Render URL and test `/health`.

The included Render configuration:
- Runs Flask with Gunicorn.
- Creates the SQLite database automatically when the app starts.
- Stores the SQLite database on a 1 GB persistent disk at `/var/data/complaints.db`.
- Generates a secure `SECRET_KEY` in Render.
- Keeps admin credentials outside the source code through environment variables.

## Important

This SQLite setup is suitable for a college/demo deployment. For a larger multi-user production system, migrate the database to PostgreSQL.
