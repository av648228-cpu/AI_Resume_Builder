# Resume Studio — AI Resume Builder

A minimal student resume builder built with Python 3.11, Flask, Jinja2, SQLAlchemy, SQLite, vanilla HTML/CSS/JavaScript, and WeasyPrint. The same `resume_template.html` and `resume.css` are used for the browser preview and PDF, keeping the exported resume aligned with the A4 preview.

## Features

- Landing page, multi-section resume builder, repeatable education/experience/project/certification rows, and A4 preview.
- PDF export via WeasyPrint using `@page { size: A4; margin: 0.75in; }` and print-color adjustment.
- JPG/JPEG/PNG profile photo upload (maximum 2 MB) and separately stored supporting documents (PDF/JPG/JPEG/PNG, maximum 4 MB per file and five per save). Supporting documents are not displayed or linked on the resume.
- Grouped skills, validated HTTP(S) links, bullet descriptions, and browser-side indexed form names after rows are added or removed.
- Text import using local regular-expression/rule-based parsing. OpenAI parsing and description improvement are optional and degrade gracefully when `OPENAI_API_KEY` is not configured or the provider is unavailable.
- SQLite by default; SQLAlchemy-compatible PostgreSQL URLs are supported when `DATABASE_URL` is supplied.
- Dockerfile for Linux deployments with WeasyPrint's system libraries, plus a Procfile for Python buildpack platforms.

## Requirements

- Python 3.11
- For native local PDF generation, WeasyPrint's system libraries are required; see [WeasyPrint installation documentation](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html).
- Docker is optional for local development, but recommended for Render/Railway deployments because it installs the PDF-rendering system libraries.

## Local setup

### 1. Create and activate a virtual environment

**Windows PowerShell**

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

**Linux/macOS**

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and set `SECRET_KEY` to a long random value. OpenAI is optional; keep `OPENAI_API_KEY` blank to use local parsing only. The app loads `.env` via `python-dotenv`.

### 2. Install WeasyPrint system dependencies

- **Ubuntu/Debian:** install Pango and the font/rendering libraries before installing Python packages:

  ```bash
  sudo apt-get update
  sudo apt-get install -y libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 libharfbuzz0b libfontconfig1 libgdk-pixbuf-2.0-0 shared-mime-info fonts-liberation
  python -m pip install -r requirements.txt
  python -m weasyprint --info
  ```

- **macOS with Homebrew:**

  ```bash
  brew install pango cairo gdk-pixbuf libffi fontconfig
  python -m pip install -r requirements.txt
  python -m weasyprint --info
  ```

- **Windows:** WeasyPrint's Python package needs Pango and related native libraries; see the official setup guide. If the PDF endpoint is all you need to test immediately, run the project in Docker instead.

### 3. Run the app

```bash
python app.py
```

Open <http://127.0.0.1:5000>. The SQLite database is created under Flask's `instance/` folder, and uploads are saved under `uploads/`. To run using the production WSGI server locally:

```bash
gunicorn app:app --bind 127.0.0.1:5000 --workers 2 --timeout 120
```

### 4. Run in Docker (optional)

```bash
docker build -t resume-studio .
docker run --rm -p 5000:10000 -e PORT=10000 -e SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')" resume-studio
```

Then open <http://127.0.0.1:5000>.

## Deploy to Render

The included `Dockerfile` is the recommended option because it installs the native libraries required by WeasyPrint.

1. Push the entire `resume-builder/` directory to a Git repository.
2. In Render, choose **New + → Web Service** and connect the repository.
3. Choose **Docker** as the runtime so Render builds the supplied `Dockerfile`.
4. Add these environment variables in the service settings:
   - `SECRET_KEY`: a unique random string.
   - `OPENAI_API_KEY`: optional; leave blank to disable OpenAI features.
   - `OPENAI_MODEL`: optional; defaults to `gpt-4o-mini`.
   - `DATABASE_URL`: optional; if omitted, SQLite uses the container's local instance directory.
   - `UPLOAD_FOLDER`: optional; defaults to `/app/uploads` in the container.
5. Deploy. Render supplies `PORT`; the Docker start command binds to it. Optionally set the health check path to `/`.
6. **Persist files in production:** the container filesystem can be ephemeral. Attach a persistent disk (for example, mounted at `/app/data`) and configure `UPLOAD_FOLDER=/app/data/uploads` and `DATABASE_URL=sqlite:////app/data/resume_builder.db`. Confirm the mounted path is writable by the app's `appuser`. For larger deployments, use a managed database and durable object storage for uploads.

Render also supports Python runtimes and the included `Procfile`, but use the Docker runtime unless you have arranged WeasyPrint's native dependencies yourself.

## Deploy to Railway

1. Push the project to GitHub or another Railway-supported source repository.
2. Create a new Railway project and deploy from that repository. Railway will detect and build the `Dockerfile`.
3. Add `SECRET_KEY` and any optional OpenAI environment variables under **Variables**.
4. For durable data, add a Railway Volume and mount it at a writable directory such as `/app/data`, then set `UPLOAD_FOLDER=/app/data/uploads` and `DATABASE_URL=sqlite:////app/data/resume_builder.db`. Verify the mounted volume's permissions match the container user.
5. Deploy and use the generated public domain. Railway provides `PORT` to the Docker start command.

## Environment variables

| Variable | Required | Purpose |
|---|---|---|
| `SECRET_KEY` | Production: yes | Signs Flask sessions and CSRF tokens. If absent, a random process-local key is generated; sessions will not survive restarts. |
| `DATABASE_URL` | No | SQLAlchemy database URL. Defaults to `sqlite:///resume_builder.db` (inside Flask's `instance/` directory). |
| `UPLOAD_FOLDER` | No | Location for profile photos and private supporting files. Defaults to the project's `uploads/` directory. |
| `OPENAI_API_KEY` | No | Enables optional AI description polishing and AI-assisted text import. |
| `OPENAI_MODEL` | No | OpenAI model name; defaults to `gpt-4o-mini`. |
| `PORT` | No | HTTP port. Set automatically by most hosting platforms; defaults to `5000` for `python app.py`. |

When using PostgreSQL, set a SQLAlchemy URL such as `postgresql+psycopg://user:password@host:5432/database`. The `psycopg[binary]` driver is included.

## Troubleshooting WeasyPrint on Linux/macOS

**`cannot load library 'libpango'`, `gobject`, or `harfbuzz`**

Install the native packages for your OS (examples above), then restart the terminal/virtual environment and run `python -m weasyprint --info`. Installing only the Python wheel is not always sufficient; WeasyPrint relies on Pango and other native libraries.

**PDF export redirects back to the preview with an error message**

Check the application logs for the native dependency error. For deployments, use the included Dockerfile or install the packages listed in the official WeasyPrint guide.

**macOS Apple Silicon / architecture mismatch**

Make sure Homebrew, Python, and the virtual environment use the same architecture. Reinstall Pango and then reinstall the Python requirements inside the matching virtual environment.

**Missing or substituted fonts**

This project requests Georgia and Helvetica/Arial, then falls back to standard serif/sans-serif fonts if those proprietary fonts are unavailable on the host. Linux Docker images install Liberation fonts as metrically similar substitutes.

**SQLite or uploads disappear after redeploy**

The default database and uploads are local files. Configure a persistent disk/volume and point `DATABASE_URL` and `UPLOAD_FOLDER` to it, or use managed database/object-storage services.

**`413 Request Entity Too Large`**

The complete multipart request is capped at 12 MB. Photos are limited to 2 MB, and each supporting document is limited to 4 MB. Upload fewer/smaller files and retry.

## Data and production notes

This starter app does not include user accounts or a resume deletion dashboard. Anyone who has a resume's unique URL can view or edit that resume, so treat the URL as private and do not store sensitive documents. For a public production service, add authentication/authorization, deletion and retention controls, upload malware scanning, rate limiting, and a privacy notice before collecting real student information.

## Project layout

```text
resume-builder/
├── app.py
├── config.py
├── models.py
├── requirements.txt
├── Procfile
├── runtime.txt
├── .python-version
├── .env.example
├── Dockerfile
├── README.md
├── utils/
│   ├── __init__.py
│   ├── pdf_export.py
│   ├── ai_helper.py
│   └── parser.py
├── templates/
│   ├── base.html
│   ├── index.html
│   ├── build.html
│   ├── preview.html
│   ├── ai_import.html
│   └── resume_template.html
├── static/
│   ├── css/style.css
│   ├── css/resume.css
│   └── js/builder.js
└── uploads/.gitkeep
```
