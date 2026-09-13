import type { ChangeEvent } from "react";
import {
  type ClassId,
  displayNameFor,
  SPLIT_IDS,
  SPLIT_LABELS,
  type SplitId,
  SYSTEM_CLASSES,
} from "../domain/classes";
import type { ImageFilters } from "../domain/images";

export function FilterBar({
  filters,
  onChange,
  disabled,
}: {
  filters: ImageFilters;
  onChange: (next: ImageFilters) => void;
  disabled?: boolean;
}) {
  const onLabeled = (event: ChangeEvent<HTMLSelectElement>) => {
    const value = event.target.value;
    const labeled =
      value === "yes" || value === "no" ? value : ("all" as const);
    onChange({ ...filters, labeled });
  };
  const onClass = (event: ChangeEvent<HTMLSelectElement>) => {
    const value = event.target.value;
    onChange({
      ...filters,
      classId: value === "" ? "" : (value as ClassId),
    });
  };
  const onSplit = (event: ChangeEvent<HTMLSelectElement>) => {
    const value = event.target.value;
    onChange({
      ...filters,
      split: value === "" ? "" : (value as SplitId),
    });
  };

  return (
    <fieldset className="filters" disabled={disabled}>
      <legend>絞り込み</legend>
      <label>
        ラベル
        <select
          value={filters.labeled}
          onChange={onLabeled}
          data-testid="filter-labeled"
        >
          <option value="all">すべて</option>
          <option value="yes">確定ラベルあり</option>
          <option value="no">未ラベル</option>
        </select>
      </label>
      <label>
        クラス
        <select
          value={filters.classId}
          onChange={onClass}
          data-testid="filter-class"
        >
          <option value="">すべて</option>
          {SYSTEM_CLASSES.map((item) => (
            <option key={item.classId} value={item.classId}>
              {displayNameFor(item.classId)}
            </option>
          ))}
        </select>
      </label>
      <label>
        分割
        <select
          value={filters.split}
          onChange={onSplit}
          data-testid="filter-split"
        >
          <option value="">すべて</option>
          {SPLIT_IDS.map((id) => (
            <option key={id} value={id}>
              {SPLIT_LABELS[id]}
            </option>
          ))}
        </select>
      </label>
    </fieldset>
  );
}
