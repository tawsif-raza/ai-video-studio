from agents.research.contract import ResearchInput

SYSTEM_INSTRUCTION = """You are the Research agent inside an autonomous AI video studio.
Output ONLY valid JSON matching the schema below. No prose, no markdown fences.
Gather supporting context for the idea below so a story writer can ground their
script in specific, concrete detail instead of generic statements. This is
recall of what you already know, not a live web search - do not claim facts
you are not confident in.
"""


def build_research_prompt(input_data: ResearchInput) -> str:
    tone_line = f"Desired tone: {input_data.tone}\n" if input_data.tone else ""
    audience_line = f"Target audience: {input_data.audience}\n" if input_data.audience else ""
    return f"""{SYSTEM_INSTRUCTION}

Story idea: {input_data.story_idea}
{tone_line}{audience_line}
Return JSON with exactly this shape:
{{
  "key_facts": [string],
  "considerations": [string]
}}
"""
