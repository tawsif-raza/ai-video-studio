import pytest

from agents.base.exceptions import ContractViolationError
from agents.research.schema import ResearchSchema
from agents.research.validator import validate_research_brief


def _make_brief(key_facts=None, considerations=None) -> ResearchSchema:
    return ResearchSchema(
        key_facts=key_facts if key_facts is not None else ["Fact one", "Fact two"],
        considerations=considerations if considerations is not None else ["Consideration one"],
    )


def test_valid_brief_passes():
    brief = _make_brief()
    validate_research_brief(brief)


def test_zero_key_facts_rejected():
    brief = _make_brief(key_facts=[])
    with pytest.raises(ContractViolationError):
        validate_research_brief(brief)


def test_empty_key_fact_rejected():
    brief = _make_brief(key_facts=["Fact one", "   "])
    with pytest.raises(ContractViolationError):
        validate_research_brief(brief)


def test_empty_consideration_rejected():
    brief = _make_brief(considerations=[""])
    with pytest.raises(ContractViolationError):
        validate_research_brief(brief)


def test_empty_considerations_list_is_allowed():
    brief = _make_brief(considerations=[])
    validate_research_brief(brief)
