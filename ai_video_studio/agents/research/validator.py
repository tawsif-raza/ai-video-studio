from agents.base.exceptions import ContractViolationError
from agents.research.schema import ResearchSchema


def validate_research_brief(brief: ResearchSchema) -> ResearchSchema:
    if not brief.key_facts:
        raise ContractViolationError("Research brief has zero key facts")

    if any(not fact.strip() for fact in brief.key_facts):
        raise ContractViolationError("Research brief contains an empty key fact")

    if any(not c.strip() for c in brief.considerations):
        raise ContractViolationError("Research brief contains an empty consideration")

    return brief
