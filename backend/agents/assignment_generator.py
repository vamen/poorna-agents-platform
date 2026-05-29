"""Assignment Generator agent — creates a tailored technical assignment from a resume profile.

Takes the structured profile from PdfParserAgent and uses Claude to generate
a 2–3 hour take-home assignment that directly tests the candidate's claimed
experience.

Events emitted:
    assignment_generator.assignment.ready   {to_email, candidate_name, subject,
                                              assignment_text, original_payload}
    assignment_generator.generation.failed  {reason, original_payload}

Agent config:
    company_name   — name to use in the assignment header (default: "Agent Platform")
    role           — role being hired for (default: inferred from resume)
"""

from __future__ import annotations

import logging

from agents.base import BaseAgent

logger = logging.getLogger(__name__)


class AssignmentGeneratorAgent(BaseAgent):
    agent_type = "assignment_generator"

    async def run(self, event_name: str, payload: dict) -> dict:
        candidate_email = payload.get("candidate_email", "")
        candidate_name = payload.get("candidate_name", "Candidate")
        current_role = payload.get("current_role", "Software Engineer")
        skills = payload.get("skills", [])
        experience_summary = payload.get("experience_summary", "")
        years_exp = payload.get("years_of_experience", 0)

        if not candidate_email:
            return {
                "event": "assignment_generator.generation.failed",
                "payload": {
                    "reason": "No candidate email found in parsed resume",
                    "original_payload": payload,
                },
            }

        company_name = self.config.get("company_name", "Agent Platform")
        role = self.config.get("role", current_role)

        try:
            assignment_text = await self._generate_assignment(
                candidate_name=candidate_name,
                role=role,
                skills=skills,
                experience_summary=experience_summary,
                years_exp=years_exp,
                company_name=company_name,
            )
        except Exception as exc:
            logger.error("Assignment generation failed: %s", exc)
            return {
                "event": "assignment_generator.generation.failed",
                "payload": {"reason": str(exc), "original_payload": payload},
            }

        subject = f"Technical Assignment — {role} at {company_name}"

        logger.info(
            "Assignment generated for %s <%s> applying for %s",
            candidate_name, candidate_email, role,
        )

        return {
            "event": "assignment_generator.assignment.ready",
            "payload": {
                "to_email": candidate_email,
                "candidate_name": candidate_name,
                "subject": subject,
                "assignment_text": assignment_text,
                "original_payload": payload,
            },
        }

    # ── helpers ──────────────────────────────────────────────────────────────

    async def _generate_assignment(
        self,
        candidate_name: str,
        role: str,
        skills: list[str],
        experience_summary: str,
        years_exp: int,
        company_name: str,
    ) -> str:
        client = self._get_llm_client()

        skills_str = ", ".join(skills[:12]) if skills else "general software engineering"

        prompt = f"""You are a senior engineering hiring manager at {company_name}.

You are creating a take-home technical assignment for a candidate with the following profile:
- Name: {candidate_name}
- Applying for: {role}
- Years of experience: {years_exp}
- Key skills: {skills_str}
- Background: {experience_summary}

Create a focused 2–3 hour take-home assignment that:
1. Directly tests their claimed expertise (don't give a generic CRUD task to a distributed systems engineer)
2. Has a clear problem statement with context
3. Lists specific deliverables (code, design doc, or both)
4. Includes evaluation criteria so the candidate knows what matters
5. Is scoped tightly — solvable in 2–3 hours, not a week

Format the assignment as a professional email body (plain text, no markdown headers).
Start with "Hi {candidate_name}," and end with a deadline (one week from today) and contact details placeholder.
Do not use bullet points with dashes — use numbered lists for deliverables."""

        response = client.chat.completions.create(
            model="claude-sonnet-4-5",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content.strip()
