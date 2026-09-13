"""Fixed 8-class catalogue (SRS 3.5.2 / REQ-DATA-002)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class ClassSpec:
    class_id: str
    display_name: str
    display_order: int


# display_order 昇順。混同ペアが隣接する並び（SRS 3.5.2）。
SYSTEM_CLASSES: tuple[ClassSpec, ...] = (
    ClassSpec("samoyed", "サモエド", 1),
    ClassSpec("great_pyrenees", "グレート・ピレニーズ", 2),
    ClassSpec("boxer", "ボクサー", 3),
    ClassSpec("american_bulldog", "アメリカン・ブルドッグ", 4),
    ClassSpec("chihuahua", "チワワ", 5),
    ClassSpec("miniature_pinscher", "ミニチュア・ピンシャー", 6),
    ClassSpec("pomeranian", "ポメラニアン", 7),
    ClassSpec("havanese", "ハバニーズ", 8),
)

CLASS_IDS: tuple[str, ...] = tuple(item.class_id for item in SYSTEM_CLASSES)

ClassId = Literal[
    "samoyed",
    "great_pyrenees",
    "boxer",
    "american_bulldog",
    "chihuahua",
    "miniature_pinscher",
    "pomeranian",
    "havanese",
]

LabelSource = Literal["human", "model_suggested"]
Split = Literal["train", "val", "test", "unassigned"]
SPLIT_IDS: tuple[str, ...] = ("train", "val", "test", "unassigned")
