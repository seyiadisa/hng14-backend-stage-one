from enum import Enum


class AgeGroup(str, Enum):
    child = "child"
    teenager = "teenager"
    adult = "adult"
    senior = "senior"
