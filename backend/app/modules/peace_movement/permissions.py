"""Permission codes of the Peace Movement (docs/modules/peace-movement.md)."""

from enum import StrEnum


class PeacePerm(StrEnum):
    MEMBER_READ = "peace_movement.member.read"
    MEMBER_WRITE = "peace_movement.member.write"
    MEMBER_VALIDATE = "peace_movement.member.validate"
    MEMBER_REASSIGN = "peace_movement.member.reassign"
    MEMBER_IMPORT = "peace_movement.member.import"
    HOUSE_READ = "peace_movement.house.read"
    HOUSE_WRITE = "peace_movement.house.write"
    HOUSE_REASSIGN_CREDIT = "peace_movement.house.reassign_credit"
    HOUSE_LINK = "peace_movement.house.link"
    STATS_READ = "peace_movement.stats.read"
    GOAL_MANAGE = "peace_movement.goal.manage"
