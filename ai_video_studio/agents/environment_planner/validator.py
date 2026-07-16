from agents.base.exceptions import ContractViolationError
from agents.environment_planner.contract import get_unique_settings
from agents.environment_planner.schema import EnvironmentPlannerSchema
from agents.story_planner.contract import ProductionPlan


def validate_environment_sheet(
    environment_sheet: EnvironmentPlannerSchema,
    production_plan: ProductionPlan,
) -> EnvironmentPlannerSchema:
    """
    Confirms the sheet has exactly one profile per unique setting in the Production
    Plan - same missing/extra/duplicate checks as Character Planner, just keyed on
    setting strings instead of character names.
    """
    expected_settings = set(get_unique_settings(production_plan))
    profiled_settings = [p.setting for p in environment_sheet.environment_profiles]

    missing = expected_settings - set(profiled_settings)
    if missing:
        raise ContractViolationError(f"Environment sheet is missing profile(s) for: {sorted(missing)}")

    extra = set(profiled_settings) - expected_settings
    if extra:
        raise ContractViolationError(f"Environment sheet profiles unknown setting(s): {sorted(extra)}")

    if len(profiled_settings) != len(set(profiled_settings)):
        raise ContractViolationError("Environment sheet has duplicate profiles for the same setting")

    return environment_sheet
