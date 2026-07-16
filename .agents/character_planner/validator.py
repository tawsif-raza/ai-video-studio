from agents.base.exceptions import ContractViolationError
from agents.character_planner.schema import CharacterPlannerSchema
from agents.story_planner.contract import ProductionPlan


def validate_character_sheet(
    character_sheet: CharacterPlannerSchema,
    production_plan: ProductionPlan,
) -> CharacterPlannerSchema:
    """
    Checks the character sheet actually covers every character the Production Plan
    named — nothing missing, nothing extra, nothing duplicated.
    """
    expected_names = {c.name for c in production_plan.characters}
    profiled_names = [p.name for p in character_sheet.character_profiles]

    missing = expected_names - set(profiled_names)
    if missing:
        raise ContractViolationError(f"Character sheet is missing profile(s) for: {sorted(missing)}")

    extra = set(profiled_names) - expected_names
    if extra:
        raise ContractViolationError(f"Character sheet profiles unknown character(s): {sorted(extra)}")

    if len(profiled_names) != len(set(profiled_names)):
        raise ContractViolationError("Character sheet has duplicate profiles for the same character")

    return character_sheet