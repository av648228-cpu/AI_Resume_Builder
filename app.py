"""Flask app for building, previewing, importing, and exporting resumes."""

import base64
import hmac
import io
import os
import logging
import mimetypes
import re
import secrets
import uuid
from pathlib import Path

from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    send_from_directory,
    session,
    url_for,
)
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename

from config import Config
from models import Resume, db
from utils.ai_helper import improve_description, parse_resume_with_ai
from utils.parser import (
    clean_bullets,
    empty_resume_data,
    normalize_http_url,
    parse_resume_text,
    parse_skill_groups,
)
from utils.pdf_export import create_pdf

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png"}
DOCUMENT_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}
PERSONAL_FIELDS = (
    "name", "phone", "email", "linkedin", "github", "instagram",
    "portfolio", "location",
)
ROW_FIELDS = {
    "education": (
        "institution", "degree", "field", "location", "start_date", "end_date",
        "details",
    ),
    "experience": (
        "company", "role", "location", "start_date", "end_date", "description"
    ),
    "projects": ("name", "tech_stack", "link", "description"),
    "certifications": ("name", "issuer", "date", "credential_url"),
}


def create_app(test_config=None):
    """Create and configure the Flask application."""
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    if not os.environ.get("VERCEL"):
         Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    db.init_app(app)

    with app.app_context():
        db.create_all()

    @app.context_processor
    def inject_template_helpers():
        """Make the per-session CSRF token generator available to templates."""
        return {"csrf_token": _csrf_token}

    @app.before_request
    def validate_csrf_token():
        """Reject state-changing requests without a matching session token."""
        if request.method != "POST":
            return None
        expected = session.get("_csrf_token", "")
        submitted = request.form.get("csrf_token") or request.headers.get(
            "X-CSRFToken", ""
        )
        if (
            not expected
            or not submitted
            or not hmac.compare_digest(expected, submitted)
        ):
            abort(
                400,
                description=(
                    "Your session token was missing or expired. "
                    "Refresh and try again."
                ),
            )
        return None

    @app.after_request
    def add_security_headers(response):
        """Set conservative browser security headers for the application."""
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault(
            "Referrer-Policy", "strict-origin-when-cross-origin"
        )
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        return response

    @app.errorhandler(RequestEntityTooLarge)
    def request_too_large(_error):
        """Show a friendly message when a request exceeds the size limit."""
        return (
            render_template(
                "index.html",
                error=(
                    "The upload is too large. "
                    "Keep the full request under 12 MB."
                ),
            ),
            413,
        )

    @app.get("/")
    def index():
        """Render the product landing page."""
        return render_template("index.html", error=None)

    @app.route("/build", methods=["GET", "POST"])
    def build():
        """Render the builder and persist submitted resume details."""
        resume_id = (
            request.args.get("resume_id", "").strip()
            if request.method == "GET"
            else ""
        )
        if request.method == "GET":
            record = db.session.get(Resume, resume_id) if resume_id else None
            if resume_id and record is None:
                abort(404)
            data = record.get_data() if record else empty_resume_data()
            data = _ensure_builder_rows(data)
            return render_template(
                "build.html",
                resume=data,
                resume_id=record.id if record else "",
                error=None,
                document_count=len(record.get_documents()) if record else 0,
            )

        posted_id = request.form.get("resume_id", "").strip()
        record = db.session.get(Resume, posted_id) if posted_id else None
        if posted_id and record is None:
            abort(404)

        data = _parse_builder_form(request.form)
        existing_photo = record.photo_filename if record else None
        existing_documents = record.get_documents() if record else []
        if not data["personal"].get("name", "").strip():
            return render_template(
                "build.html",
                resume=_ensure_builder_rows(data),
                resume_id=posted_id,
                error="Full name is required.",
                document_count=len(existing_documents),
            ), 400
        try:
            photo_filename, new_documents = _save_uploads(request, app.config)
        except ValueError as exc:
            return render_template(
                "build.html",
                resume=_ensure_builder_rows(data),
                resume_id=posted_id,
                error=str(exc),
                document_count=len(existing_documents),
            ), 400

        if record is None:
            record = Resume(id=uuid.uuid4().hex)
        record.set_data(data)
        record.photo_filename = photo_filename or existing_photo
        record.set_documents(existing_documents + new_documents)

        try:
            db.session.add(record)
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            logger.exception("Unable to save resume")
            return render_template(
                "build.html",
                resume=_ensure_builder_rows(data),
                resume_id=posted_id,
                error="We could not save your resume. Please try again.",
                document_count=len(existing_documents),
            ), 500

        if (
            photo_filename
            and existing_photo
            and photo_filename != existing_photo
        ):
            _delete_upload(app.config["UPLOAD_FOLDER"], existing_photo)
        flash("Your resume has been saved.", "success")
        return redirect(url_for("preview", resume_id=record.id))

    @app.get("/preview/<resume_id>")
    def preview(resume_id):
        """Show the A4 browser preview of a saved resume."""
        record = db.session.get(Resume, resume_id)
        if record is None:
            abort(404)
        photo_url = (
            url_for("uploaded_photo", filename=record.photo_filename)
            if record.photo_filename
            else ""
        )
        return render_template(
            "preview.html",
            resume=record.get_data(),
            resume_id=record.id,
            photo_url=photo_url,
            standalone=False,
            css_text="",
        )

    @app.get("/resume/<resume_id>/pdf")
    def download_pdf(resume_id):
        """Download a PDF using the shared template and stylesheet."""
        record = db.session.get(Resume, resume_id)
        if record is None:
            abort(404)
        data = record.get_data()
        photo_url = _photo_data_uri(
            app.config["UPLOAD_FOLDER"], record.photo_filename
        )
        css_path = Path(app.static_folder) / "css" / "resume.css"
        css_text = css_path.read_text(encoding="utf-8")
        html_content = render_template(
            "resume_template.html",
            resume=data,
            photo_url=photo_url,
            css_text=css_text,
            standalone=True,
        )
        try:
            pdf_bytes = create_pdf(html_content, base_url=app.root_path)
        except Exception as exc:
            logger.exception("PDF generation failed")
            print(
                f"PDF EXPORT ERROR: {type(exc).__name__}: {exc}",
                flush=True,
            )
            flash(
                f"PDF EXPORT ERROR: {type(exc).__name__}: {exc}",
                "error",
            )
            return redirect(url_for("preview", resume_id=record.id))

        display_name = (
            data.get("personal", {}).get("name") or "student"
        ).strip()
        file_stem = secure_filename(display_name) or "student"
        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"{file_stem}-resume.pdf",
        )

    @app.get("/photo/<filename>")
    def uploaded_photo(filename):
        """Serve only files currently registered as a resume profile photo."""
        safe_name = secure_filename(filename)
        if safe_name != filename:
            abort(404)
        exists = (
            db.session.query(Resume.id)
            .filter_by(photo_filename=safe_name)
            .first()
        )
        if not exists:
            abort(404)
        return send_from_directory(
            app.config["UPLOAD_FOLDER"], safe_name, as_attachment=False
        )

    @app.route("/ai-import", methods=["GET", "POST"])
    def ai_import():
        """Parse pasted profile text into a new editable resume draft."""
        if request.method == "GET":
            return render_template(
                "ai_import.html", raw_text="", message=None, parsed=False
            )

        raw_text = request.form.get("raw_text", "").strip()
        if not raw_text:
            return render_template(
                "ai_import.html",
                raw_text=raw_text,
                message="Paste some text to import first.",
                parsed=False,
            ), 400
        if len(raw_text) > 20000:
            return render_template(
                "ai_import.html",
                raw_text=raw_text[:20000],
                message="Please keep the pasted text under 20,000 characters.",
                parsed=False,
            ), 400

        data = parse_resume_text(raw_text)
        ai_data = parse_resume_with_ai(
            raw_text,
            app.config.get("OPENAI_API_KEY", ""),
            app.config.get("OPENAI_MODEL", "gpt-4o-mini"),
        )
        if isinstance(ai_data, dict):
            data = _merge_import_data(data, ai_data)
            message = (
                "Imported with AI-assisted extraction. "
                "Review every field before using the resume."
            )
        elif app.config.get("OPENAI_API_KEY"):
            message = (
                "Imported using local parsing. AI extraction was unavailable, "
                "so please review the fields."
            )
        else:
            message = (
                "Imported using local parsing. Add OPENAI_API_KEY "
                "to enable optional AI extraction."
            )

        record = Resume(id=uuid.uuid4().hex)
        record.set_data(data)
        record.set_documents([])
        db.session.add(record)
        db.session.commit()
        flash(message, "success")
        return redirect(url_for("build", resume_id=record.id))

    @app.post("/api/improve-description")
    def api_improve_description():
        """Return a polished description when OpenAI is configured."""
        payload = request.get_json(silent=True) or {}
        description = str(payload.get("description", ""))[:5000]
        context = str(payload.get("context", "Student resume"))[:300]
        result = improve_description(
            description,
            app.config.get("OPENAI_API_KEY", ""),
            app.config.get("OPENAI_MODEL", "gpt-4o-mini"),
            context,
        )
        return jsonify(result)

    return app


def _csrf_token():
    """Get or create this browser session's CSRF token."""
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_urlsafe(32)
    return session["_csrf_token"]


def _parse_builder_form(form):
    """Convert indexed form controls into structured resume data."""
    data = empty_resume_data()
    personal = {}
    for field in PERSONAL_FIELDS:
        value = (form.get(field) or "").strip()
        if field in {"linkedin", "github", "instagram", "portfolio"}:
            value = normalize_http_url(value)
        personal[field] = value
    data["personal"] = personal

    for section, fields in ROW_FIELDS.items():
        rows = []
        for row in _extract_rows(form, section, fields):
            if not any(str(value).strip() for value in row.values()):
                continue
            if section == "experience":
                row["bullets"] = clean_bullets(row.get("description", ""))
            elif section == "projects":
                row["link"] = normalize_http_url(row.get("link", ""))
                row["bullets"] = clean_bullets(row.get("description", ""))
            elif section == "certifications":
                row["credential_url"] = normalize_http_url(
                    row.get("credential_url", "")
                )
            rows.append(row)
        data[section] = rows

    data["skills_raw"] = (form.get("skills") or "").strip()
    data["skill_groups"] = parse_skill_groups(data["skills_raw"])
    return data


def _ensure_builder_rows(data):
    """Ensure repeatable form sections contain an editable blank row."""
    defaults = empty_resume_data()
    if not isinstance(data, dict):
        data = defaults
    else:
        data = dict(data)
    for section in ROW_FIELDS:
        if not data.get(section):
            data[section] = defaults[section]
    data.setdefault("personal", defaults["personal"])
    data.setdefault("skills_raw", "")
    data.setdefault("skill_groups", [])
    return data


def _extract_rows(form, section, fields):
    """Read only valid indexed fields for one repeatable form section."""
    pattern = re.compile(rf"^{re.escape(section)}-(\d+)-([a-z_]+)$")
    indexes = set()
    for key in form.keys():
        match = pattern.match(key)
        if match and match.group(2) in fields:
            indexes.add(int(match.group(1)))

    rows = []
    for index in sorted(indexes):
        rows.append(
            {
                field: (form.get(f"{section}-{index}-{field}") or "").strip()
                for field in fields
            }
        )
    return rows


def _file_size(upload):
    """Measure an upload without trusting browser-reported size metadata."""
    stream = upload.stream
    current_position = stream.tell()
    stream.seek(0, 2)
    size = stream.tell()
    stream.seek(current_position)
    return size


def _save_uploads(request_object, config):
    """Validate and save a photo/documents; return private filenames."""
    photo = request_object.files.get("photo")
    if photo and photo.filename:
        safe_original = secure_filename(photo.filename)
        extension = Path(safe_original).suffix.lower()
        if not safe_original or extension not in PHOTO_EXTENSIONS:
            raise ValueError(
                "Profile photo must be a JPG, JPEG, or PNG image."
            )
        if _file_size(photo) > config["MAX_PHOTO_SIZE"]:
            raise ValueError("Profile photo must be 2 MB or smaller.")

    candidates = [
        item
        for item in request_object.files.getlist("documents")
        if item and item.filename
    ]
    if len(candidates) > config["MAX_DOCUMENTS_PER_REQUEST"]:
        raise ValueError("Upload up to five supporting documents per save.")
    clean_documents = []
    for item in candidates:
        safe_original = secure_filename(item.filename)
        extension = Path(safe_original).suffix.lower()
        if not safe_original or extension not in DOCUMENT_EXTENSIONS:
            raise ValueError(
                "Supporting documents must be PDF, JPG, JPEG, or PNG files."
            )
        if _file_size(item) > config["MAX_DOCUMENT_SIZE"]:
            raise ValueError(
                "Each supporting document must be 4 MB or smaller."
            )
        clean_documents.append((item, safe_original, extension))

    photo_filename = None
    upload_folder = Path(config["UPLOAD_FOLDER"])
    upload_folder.mkdir(parents=True, exist_ok=True)
    if photo and photo.filename:
        safe_original = secure_filename(photo.filename)
        extension = Path(safe_original).suffix.lower()
        photo_filename = f"{uuid.uuid4().hex}{extension}"
        photo.save(upload_folder / photo_filename)

    documents = []
    for item, safe_original, extension in clean_documents:
        stored_name = f"{uuid.uuid4().hex}{extension}"
        item.save(upload_folder / stored_name)
        documents.append(
            {"filename": stored_name, "original_name": safe_original}
        )
    return photo_filename, documents


def _delete_upload(upload_folder, filename):
    """Remove an old photo after a replacement succeeds."""
    try:
        path = Path(upload_folder) / secure_filename(filename)
        path.unlink(missing_ok=True)
    except OSError:
        logger.warning("Could not remove replaced upload %s", filename)


def _photo_data_uri(upload_folder, filename):
    """Embed a registered photo as a data URI for offline PDF rendering."""
    if not filename:
        return ""
    safe_name = secure_filename(filename)
    path = Path(upload_folder) / safe_name
    if safe_name != filename or not path.is_file():
        return ""
    mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
    try:
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"
    except OSError:
        logger.warning("Unable to read profile photo %s", filename)
        return ""


def _merge_import_data(base, ai_data):
    """Merge AI fields into the regex parse using allowlisted keys only."""
    merged = empty_resume_data()
    if isinstance(base, dict):
        merged.update(base)
    base_personal = base.get("personal", {}) if isinstance(base, dict) else {}
    ai_personal = (
        ai_data.get("personal", {})
        if isinstance(ai_data.get("personal"), dict)
        else {}
    )
    personal = empty_resume_data()["personal"]
    for field in PERSONAL_FIELDS:
        candidate = ai_personal.get(field) or base_personal.get(field, "")
        candidate = (
            str(candidate).strip()[:500] if candidate is not None else ""
        )
        if field in {"linkedin", "github", "instagram", "portfolio"}:
            candidate = normalize_http_url(candidate)
        personal[field] = candidate
    merged["personal"] = personal

    for section, fields in ROW_FIELDS.items():
        candidate_rows = ai_data.get(section)
        base_rows = base.get(section, []) if isinstance(base, dict) else []
        rows = (
            candidate_rows
            if isinstance(candidate_rows, list) and candidate_rows
            else base_rows
        )
        normalized_rows = []
        for candidate in rows[:30] if isinstance(rows, list) else []:
            if not isinstance(candidate, dict):
                continue
            row = {
                field: str(candidate.get(field, "") or "").strip()[:3000]
                for field in fields
            }
            if section in {"experience", "projects"}:
                candidate_bullets = candidate.get("bullets", [])
                if (
                    not row.get("description")
                    and isinstance(candidate_bullets, list)
                ):
                    row["description"] = "\n".join(
                        str(item).strip()
                        for item in candidate_bullets
                        if str(item).strip()
                    )
                row["bullets"] = clean_bullets(row.get("description", ""))
            if section == "projects":
                row["link"] = normalize_http_url(row.get("link", ""))
            elif section == "certifications":
                row["credential_url"] = normalize_http_url(
                    row.get("credential_url", "")
                )
            normalized_rows.append(row)
        if not normalized_rows:
            normalized_rows = empty_resume_data()[section]
        merged[section] = normalized_rows

    raw_skills = str(
        ai_data.get("skills_raw") or base.get("skills_raw", "") or ""
    ).strip()[:3000]
    merged["skills_raw"] = raw_skills
    groups = ai_data.get("skill_groups")
    if isinstance(groups, list):
        safe_groups = []
        for group in groups[:20]:
            if not isinstance(group, dict):
                continue
            label = str(group.get("name", "Skills") or "Skills").strip()[:80]
            items = group.get("items", [])
            if isinstance(items, list):
                safe_items = [
                    str(item).strip()[:100]
                    for item in items[:40]
                    if str(item).strip()
                ]
                if safe_items:
                    safe_groups.append({"name": label, "items": safe_items})
        merged["skill_groups"] = safe_groups or parse_skill_groups(raw_skills)
    else:
        merged["skill_groups"] = parse_skill_groups(raw_skills)
    return merged


app = create_app()


if __name__ == "__main__":
    import os

    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "5000")),
        debug=False,
    )
