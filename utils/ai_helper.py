"""Optional OpenAI helpers with graceful local fallbacks."""

import json
import logging

logger = logging.getLogger(__name__)


def improve_description(description, api_key, model="gpt-4o-mini", context=""):
    """Polish a description without inventing experience or achievements."""
    description = (description or "").strip()
    if not api_key:
        return {
            "success": False,
            "text": description,
            "message": (
                "AI improvement is disabled. "
                "Add OPENAI_API_KEY to enable it."
            ),
        }
    if not description:
        return {
            "success": False,
            "text": "",
            "message": "Enter a description first.",
        }

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model or "gpt-4o-mini",
            temperature=0.4,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a careful resume editor for students and "
                        "early-career candidates. "
                        "Improve clarity, grammar, and action verbs. "
                        "Preserve the original meaning. "
                        "Do not invent metrics, tools, responsibilities, "
                        "awards, or results. "
                        "Return concise plain text, preferably 2-4 bullet "
                        "lines, "
                        "without markdown fences."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Context: {context or 'Student resume'}"
                        f"\n\nText to improve:\n{description}"
                    ),
                },
            ],
        )
        improved = (response.choices[0].message.content or "").strip()
        if not improved:
            raise ValueError("The AI response was empty.")
        return {
            "success": True,
            "text": improved,
            "message": "Description improved.",
        }
    except Exception as exc:  # Optional AI must not break the builder.
        logger.warning("Description improvement unavailable: %s", exc)
        return {
            "success": False,
            "text": description,
            "message": (
                "AI is temporarily unavailable. "
                "Your original description is unchanged."
            ),
        }


def parse_resume_with_ai(raw_text, api_key, model="gpt-4o-mini"):
    """Parse pasted profile text into the app's structured resume shape."""
    if not api_key:
        return None
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        schema_instructions = {
            "personal": {
                "name": "", "phone": "", "email": "",
                "linkedin": "", "github": "",
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
                "name": "", "issuer": "", "date": "",
                "credential_url": "",
            }],
        }
        response = client.chat.completions.create(
            model=model or "gpt-4o-mini",
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Extract only information stated in the text. "
                        "Never invent facts. "
                        "Return JSON with this structure; use empty strings "
                        "and empty arrays for "
                        f"missing information: "
                        f"{json.dumps(schema_instructions)}"
                    ),
                },
                {"role": "user", "content": raw_text[:20000]},
            ],
        )
        raw_json = response.choices[0].message.content or "{}"
        parsed = json.loads(raw_json)
        return parsed if isinstance(parsed, dict) else None
    except Exception as exc:  # Use regex if optional AI parsing fails.
        logger.warning("AI resume import unavailable: %s", exc)
        return None
