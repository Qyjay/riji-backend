"""记忆使用场景权限。"""

SCENARIO_VISIBILITIES = {
    "chat": ["private", "avatar_only"],
    "avatar_comment": ["private", "avatar_only"],
    "profile_generation": ["private", "avatar_only"],
    "diary_generation": ["private"],
    "plaza_match": ["match_card", "school", "public"],
    "agent_to_agent": ["match_card", "school", "public"],
}


def allowed_visibilities_for_scenario(scenario: str) -> list[str]:
    return SCENARIO_VISIBILITIES.get(scenario, ["private"])
