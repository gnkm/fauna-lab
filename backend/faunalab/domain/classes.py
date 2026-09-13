"""Fixed 8-class catalogue (SRS 3.5.2 / REQ-DATA-002)."""

from __future__ import annotations

from dataclasses import dataclass


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
