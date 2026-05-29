"""Classifier agent — classifies email body using Claude.

Events emitted:
    classification.done    {category, confidence, reasoning, original_payload}
    classification.failed  {reason, original_payload}

Agent config:
    categories   — list of category names, e.g. ["weather", "other"]
    criteria     — human-readable description of what to classify
"""

from __future__ import annotations

import json
import logging

from agents.base import BaseAgent

logger = logging.getLogger(__name__)

DEFAULT_CATEGORIES = ["weather", "other"]
DEFAULT_CRITERIA = "Does the email body discuss weather, temperature, rain, storms, or climate?"


class ClassifierAgent(BaseAgent):
    agent_type = "classifier"

    async def run(self, event_name: str, payload: dict) -> dict:
        categories = self.config.get("categories", DEFAULT_CATEGORIES)
        criteria = self.config.get("criteria", DEFAULT_CRITERIA)

        body = payload.get("body", "")
        subject = payload.get("subject", "")
        sender = payload.get("sender", "")

        if not body and not subject:
            return {
                "event": "classifier.classification.failed",
                "payload": {
                    "reason": "No body or subject to classify",
                    "original_payload": payload,
                },
            }

        client = self._get_llm_client()

        prompt = f"""You are an email classifier. Classify the following email into one of these categories: {categories}

Criteria: {criteria}

Email:
Subject: {subject}
From: {sender}
Body:
{body[:2000]}

Respond with a JSON object (no markdown, raw JSON only):
{{
  "category": "<one of the categories>",
  "confidence": <0.0-1.0>,
  "reasoning": "<one sentence>"
}}"""

        try:
            response = client.chat.completions.create(
                model="claude-haiku-4-5",
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.choices[0].message.content.strip()
            # Strip markdown code fences if model wraps response
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()
            result = json.loads(raw)
            category = result.get("category", "other")
            confidence = float(result.get("confidence", 0.5))
            reasoning = result.get("reasoning", "")
        except Exception as exc:
            logger.error("Classifier LLM call failed: %s", exc)
            return {
                "event": "classifier.classification.failed",
                "payload": {
                    "reason": str(exc),
                    "original_payload": payload,
                },
            }

        logger.info("Classified as '%s' (confidence=%.2f): %s", category, confidence, reasoning)

        return {
            "event": "classifier.classification.done",
            "payload": {
                "category": category,
                "confidence": confidence,
                "reasoning": reasoning,
                "original_payload": payload,
            },
        }
