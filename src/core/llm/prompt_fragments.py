"""Shared instruction fragments reused verbatim across agent system prompts.

Extracting these avoids the same policy line drifting into slightly different
wording per prompt (e.g. "Return JSON only." vs. "Return structured JSON
only — no markdown, no prose outside schema fields.") and is the natural
place to grow a genuinely shared static prefix if prompt caching consolidation
is pursued later.
"""

JSON_ONLY_INSTRUCTION = "Return structured JSON only — no markdown, no prose outside schema fields."
