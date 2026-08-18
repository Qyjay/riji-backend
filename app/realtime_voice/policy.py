"""实时语音工具风险等级与暴露策略。"""
from enum import Enum


class ToolRisk(str, Enum):
    R0 = "R0"  # 只读
    R1 = "R1"  # 私有、可撤销草稿
    R2 = "R2"  # 私有业务动作，需要确认
    R3 = "R3"  # 公开、关系或承诺，不允许暴露给实时模型


class ToolPolicyError(ValueError):
    pass


def ensure_tool_can_be_exposed(risk: ToolRisk) -> None:
    if risk == ToolRisk.R3:
        raise ToolPolicyError("R3 工具不能注册到实时语音模型")


def tool_requires_confirmation(risk: ToolRisk) -> bool:
    return risk == ToolRisk.R2
