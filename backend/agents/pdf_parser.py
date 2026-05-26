"""PDF Parser agent — extracts structured data from a resume PDF.

Receives an email payload (from GmailWatcher) that includes a base64-encoded
PDF attachment.  Uses pypdf for text extraction and Claude to pull out the
structured candidate profile.

Events emitted:
    pdf_parser.resume.parsed   {candidate_email, candidate_name, years_of_experience,
                                 current_role, skills, experience_summary, raw_text}
    pdf_parser.parse.failed    {reason, original_payload}

Agent config:
    (none required — uses platform Anthropic key)
"""

from __future__ import annotations

import base64
import io
import json
import logging

from agents.base import BaseAgent

logger = logging.getLogger(__name__)


class PdfParserAgent(BaseAgent):
    agent_type = "pdf_parser"

    async def run(self, event_name: str, payload: dict) -> dict:
        # Support arriving directly from GmailWatcher OR via a Classifier node.
        # Classifier wraps the original email as original_payload.
        email_payload = payload
        if "original_payload" in payload and "attachments" not in payload:
            email_payload = payload["original_payload"]

        attachments = email_payload.get("attachments", [])

        # Find the first PDF attachment
        pdf_b64 = None
        pdf_filename = "resume.pdf"
        for att in attachments:
            mime = att.get("mime_type", "")
            name = att.get("filename", "").lower()
            if "pdf" in mime or name.endswith(".pdf"):
                pdf_b64 = att.get("data_b64", "")
                pdf_filename = att.get("filename", pdf_filename)
                break

        if not pdf_b64:
            return {
                "event": "pdf_parser.parse.failed",
                "payload": {
                    "reason": "No PDF attachment found in email",
                    "original_payload": payload,
                },
            }

        # Decode and extract text
        try:
            pdf_bytes = base64.b64decode(pdf_b64)
            raw_text = self._extract_text(pdf_bytes)
        except Exception as exc:
            logger.error("PDF text extraction failed: %s", exc)
            return {
                "event": "pdf_parser.parse.failed",
                "payload": {"reason": f"PDF extraction error: {exc}", "original_payload": payload},
            }

        if not raw_text.strip():
            return {
                "event": "pdf_parser.parse.failed",
                "payload": {"reason": "PDF yielded no text", "original_payload": payload},
            }

        # Use Claude to extract structured profile
        try:
            profile = await self._extract_profile(raw_text)
        except Exception as exc:
            logger.error("Claude profile extraction failed: %s", exc)
            return {
                "event": "pdf_parser.parse.failed",
                "payload": {"reason": f"LLM extraction error: {exc}", "original_payload": payload},
            }

        logger.info(
            "Resume parsed: %s <%s>, %s yrs exp, skills: %s",
            profile.get("candidate_name"),
            profile.get("candidate_email"),
            profile.get("years_of_experience"),
            profile.get("skills", [])[:3],
        )

        return {
            "event": "pdf_parser.resume.parsed",
            "payload": {
                **profile,
                "raw_text": raw_text[:3000],   # truncated for downstream context
                "original_payload": email_payload,  # always the raw email for thread reply
            },
        }

    # ── helpers ──────────────────────────────────────────────────────────────

    def _extract_text(self, pdf_bytes: bytes) -> str:
        """Extract plain text from PDF bytes using pypdf."""
        import pypdf

        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        # Try decrypting with empty password (handles permission-locked PDFs)
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:
                raise ValueError("File has not been decrypted")
        pages = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
        return "\n".join(pages)

    async def _extract_profile(self, raw_text: str) -> dict:
        """Use Claude to extract a structured candidate profile from resume text."""
        from openai import OpenAI
        from config import settings

        client = OpenAI(
            api_key=settings.anthropic_api_key,
            base_url="https://api.anthropic.com/v1",
        )

        prompt = f"""You are a resume parser. Extract a structured profile from the following resume text.

Resume:
{raw_text[:4000]}

Respond with a JSON object (raw JSON only, no markdown):
{{
  "candidate_name": "<full name>",
  "candidate_email": "<email address>",
  "candidate_phone": "<phone if present, else null>",
  "current_role": "<most recent job title>",
  "current_company": "<most recent employer>",
  "years_of_experience": <integer, total years>,
  "skills": ["<skill1>", "<skill2>", ...],
  "experience_summary": "<2-3 sentence summary of background and strengths>"
}}"""

        response = client.chat.completions.create(
            model="claude-haiku-4-5",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        return json.loads(raw)
