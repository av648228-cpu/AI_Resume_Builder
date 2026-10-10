"""Rule-based parsing helpers for builder forms and pasted resume text."""

import re
from urllib.parse import urlparse


SECTION_ALIASES = {
    "education": {
        "education", "academic background", "academics", "qualification"
    },
    "experience": {
        "experience", "work experience", "professional experience",
        "employment",
        "internships", "internship experience",
    },
    "projects": {"projects", "personal projects", "academic projects"},
    "skills": {"skills", "technical skills", "core skills", "technologies"},
    "certifications": {
        "certifications", "certificates", "licenses and certifications"
    },
}


def empty_resume_data():
    """Create the complete default form shape used by Jinja templates."""
    return {
        "personal": {
            "name": "", "phone": "", "email": "", "linkedin": "", "github": "",
            "instagram": "", "portfolio": "", "location": "",
        },
        "education": [{
            "institution": "", "degree": "", "field": "", "location": "",
            "start_date": "", "end_date": "", "details": "",
        }],
        "experience": [{
            "company": "", "role": "", "location": "", "start_date": "",
            "end_date": "", "description": "", "bullets": [],
        }],
        "projects": [{
            "name": "", "tech_stack": "", "link": "",
            "description": "", "bullets": [],
        }],
        "skills_raw": "",
        "skill_groups": [],
        "certifications": [{
            "name": "", "issuer": "", "date": "", "credential_url": "",
        }],
    }


def clean_bullets(description):
    """Split a multiline description into trimmed bullet lines."""
    bullets = []
    for line in (description or "").splitlines():
        text = re.sub(r"^\s*(?:[-*•▪]|\d+[.)])\s*", "", line).strip()
        if text:
            bullets.append(text)
    return bullets


def parse_skill_groups(raw_skills):
    """Parse grouped skills such as 'Languages: Python, Java; Tools: Git'."""
    groups = []
    raw_skills = (raw_skills or "").strip()
    if not raw_skills:
        return groups

    segments = re.split(r"[;\n]+", raw_skills)
    for segment in segments:
        segment = segment.strip()
        if not segment:
            continue
        if ":" in segment:
            label, items_text = segment.split(":", 1)
            label = label.strip()
        else:
            label, items_text = "Skills", segment
        items = [
            item.strip()
            for item in re.split(r"[,|]+", items_text)
            if item.strip()
        ]
        if items:
            groups.append({"name": label or "Skills", "items": items})
    return groups


def normalize_http_url(value):
    """Normalize a URL to HTTP(S), rejecting unsafe schemes."""
    value = (value or "").strip()
    if not value:
        return ""
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", value):
        value = "https://" + value
    parsed = urlparse(value)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return ""
    return value


def _first_url(text, pattern=None):
    """Find and normalize the first URL matching an optional pattern."""
    candidates = re.findall(
        pattern or r"(?:https?://|www\.)[^\s<>]+",
        text,
        flags=re.IGNORECASE,
    )
    for candidate in candidates:
        candidate = candidate.rstrip(".,;)]}")
        normalized = normalize_http_url(candidate)
        if normalized:
            return normalized
    return ""


def _heading(line):
    """Return a normalized section key when a line looks like a heading."""
    clean = re.sub(r"[:\s]+$", "", line.strip().lower())
    clean = re.sub(r"\s+", " ", clean)
    for key, aliases in SECTION_ALIASES.items():
        if clean in aliases:
            return key
    return None


def _split_blocks(lines, split_on_non_bullet=True):
    """Split section text into entry blocks at blank lines and headings."""
    blocks = []
    current = []
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            if current:
                blocks.append(current)
                current = []
            continue
        is_bullet = bool(re.match(r"^(?:[-*•▪]|\d+[.)])\s+", line))
        is_indented = raw_line[:1].isspace()
        is_metadata = bool(
            re.match(
                r"(?:tech(?:nology)? stack|technologies|tools|built with|"
                r"location)\s*:",
                line,
                flags=re.IGNORECASE,
            )
            or re.match(r"(?:https?://|www\.)", line, flags=re.IGNORECASE)
        )
        looks_like_entry = (
            split_on_non_bullet
            and not is_bullet
            and not is_indented
            and not is_metadata
            and len(line) <= 130
        )
        if looks_like_entry and current:
            blocks.append(current)
            current = []
        current.append(line)
    if current:
        blocks.append(current)
    return blocks


def _date_parts(text):
    """Extract a simple start/end date range from a heading."""
    match = re.search(
        r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+)?"
        r"(20\d{2}|19\d{2})\s*(?:-|–|to)\s*"
        r"(Present|Current|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
        r"[a-z]*\.?\s+)?(20\d{2})?",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return "", ""
    start = " ".join(
        part for part in (match.group(1), match.group(2)) if part
    ).strip()
    end = " ".join(
        part for part in (match.group(3), match.group(4)) if part
    ).strip()
    return start, end


def parse_resume_text(raw_text):
    """Extract common resume fields from pasted profile text without an LLM."""
    text = (raw_text or "")[:20000]
    lines = [line.rstrip() for line in text.splitlines()]
    nonempty = [line.strip() for line in lines if line.strip()]
    result = empty_resume_data()
    result["education"] = []
    result["experience"] = []
    result["projects"] = []
    result["certifications"] = []

    email_match = re.search(
        r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", text, re.IGNORECASE
    )
    if email_match:
        result["personal"]["email"] = email_match.group(0)
    location_match = re.search(
        r"(?:Location|Based in)\s*:\s*([^\n|]+)",
        text,
        flags=re.IGNORECASE,
    )
    if location_match:
        result["personal"]["location"] = location_match.group(1).strip()[:120]
    phone_match = re.search(r"(?<!\w)\+?\d[\d\s().-]{7,}\d(?!\w)", text)
    if phone_match:
        result["personal"]["phone"] = re.sub(
            r"\s+", " ", phone_match.group(0)
        ).strip()

    all_urls = re.findall(r"(?:https?://|www\.)[^\s<>]+", text, re.IGNORECASE)
    for raw_url in all_urls:
        candidate = normalize_http_url(raw_url.rstrip(".,;)]}"))
        if not candidate:
            continue
        lower = candidate.lower()
        if "linkedin.com" in lower and not result["personal"]["linkedin"]:
            result["personal"]["linkedin"] = candidate
        elif "github.com" in lower and not result["personal"]["github"]:
            result["personal"]["github"] = candidate
        elif "instagram.com" in lower and not result["personal"]["instagram"]:
            result["personal"]["instagram"] = candidate
        elif not result["personal"]["portfolio"]:
            result["personal"]["portfolio"] = candidate

    ignored = set(SECTION_ALIASES.keys())
    for line in nonempty[:8]:
        if "@" in line or re.search(r"\+?\d[\d\s().-]{7,}\d", line):
            continue
        if _heading(line) or line.lower().strip(":") in ignored:
            continue
        has_url = any(
            marker in line.lower()
            for marker in ("http://", "https://", "www.")
        )
        if has_url:
            continue
        if len(line.split()) <= 6 and not line.endswith(":"):
            result["personal"]["name"] = line.strip(" |,-")
            break

    sections = {key: [] for key in SECTION_ALIASES}
    current = "general"
    for line in lines:
        heading = _heading(line.strip())
        if heading:
            current = heading
            continue
        sections.get(current, []).append(line)

    skill_lines = [
        line.strip(" -•*\t")
        for line in sections["skills"]
        if line.strip()
    ]
    result["skills_raw"] = "; ".join(skill_lines)
    result["skill_groups"] = parse_skill_groups(result["skills_raw"])

    for block in _split_blocks(
        sections["education"], split_on_non_bullet=False
    ):
        plain = [
            re.sub(r"^(?:[-*•▪]|\d+[.)])\s*", "", item).strip()
            for item in block
        ]
        if not any(plain):
            continue
        header = plain[0]
        start_date, end_date = _date_parts(" ".join(plain))
        dates_match = re.search(r"\b(?:19|20)\d{2}\b", header)
        if dates_match:
            header = header[:dates_match.start()].strip(" ,-|")
        degree = plain[1] if len(plain) > 1 else ""
        detail_lines = [
            item for item in plain[2:] if not _date_parts(item)[0]
        ]
        details = " | ".join(detail_lines)
        result["education"].append({
            "institution": header, "degree": degree,
            "field": "", "location": "",
            "start_date": start_date, "end_date": end_date, "details": details,
        })

    for block in _split_blocks(sections["experience"]):
        header = re.sub(r"^(?:[-*•▪]|\d+[.)])\s*", "", block[0]).strip()
        start_date, end_date = _date_parts(header)
        header_without_dates = re.sub(
            r"\s*\(?[^()]*\b(?:19|20)\d{2}\b[^()]*\)?\s*$",
            "",
            header,
        ).strip(" ,-|")
        if " at " in header_without_dates.lower():
            match = re.split(
                r"\s+at\s+",
                header_without_dates,
                maxsplit=1,
                flags=re.IGNORECASE,
            )
            role, company = match[0].strip(), match[1].strip()
        elif " | " in header_without_dates:
            role, company = [
                item.strip()
                for item in header_without_dates.split(" | ", 1)
            ]
        else:
            role, company = header_without_dates, ""
        bullets = clean_bullets("\n".join(block[1:]))
        result["experience"].append({
            "company": company,
            "role": role,
            "location": "",
            "start_date": start_date,
            "end_date": end_date,
            "description": "\n".join(bullets),
            "bullets": bullets,
        })

    for block in _split_blocks(sections["projects"]):
        header = re.sub(r"^(?:[-*•▪]|\d+[.)])\s*", "", block[0]).strip()
        tech_stack = ""
        project_link = ""
        description_lines = []
        for line in block[1:]:
            technology_match = re.match(
                r"(?:tech(?:nology)? stack|technologies|tools|built with)"
                r"\s*:\s*(.+)",
                line,
                flags=re.IGNORECASE,
            )
            if technology_match:
                tech_stack = technology_match.group(1).strip()
                continue
            found_link = _first_url(line)
            if found_link and not project_link:
                project_link = found_link
                remainder = re.sub(
                    r"https?://\S+|www\.\S+", "", line
                ).strip(" -|:")
                if remainder:
                    description_lines.append(remainder)
                continue
            description_lines.append(line)
        bullets = clean_bullets("\n".join(description_lines))
        result["projects"].append({
            "name": header,
            "tech_stack": tech_stack,
            "link": project_link,
            "description": "\n".join(bullets),
            "bullets": bullets,
        })

    for line in sections["certifications"]:
        clean = re.sub(r"^(?:[-*•▪]|\d+[.)])\s*", "", line).strip()
        if clean:
            result["certifications"].append({
                "name": clean, "issuer": "", "date": "", "credential_url": "",
            })

    # Keep blank entry rows available when no section was recognized.
    if not result["education"]:
        result["education"] = empty_resume_data()["education"]
    if not result["experience"]:
        result["experience"] = empty_resume_data()["experience"]
    if not result["projects"]:
        result["projects"] = empty_resume_data()["projects"]
    if not result["certifications"]:
        result["certifications"] = empty_resume_data()["certifications"]
    return result
