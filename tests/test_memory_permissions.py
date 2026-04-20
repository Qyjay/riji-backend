"""记忆场景权限测试。"""

from app.memory.permissions import allowed_visibilities_for_scenario


def test_chat_scenario_includes_private_and_avatar_only():
    assert allowed_visibilities_for_scenario("chat") == ["private", "avatar_only"]


def test_plaza_match_only_uses_public_levels():
    visibilities = allowed_visibilities_for_scenario("plaza_match")

    assert "private" not in visibilities
    assert visibilities == ["match_card", "school", "public"]


def test_unknown_scenario_defaults_to_private_only():
    assert allowed_visibilities_for_scenario("unknown-scene") == ["private"]
