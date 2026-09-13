import type { ChangeEvent } from "react";
import { type ClassId, SYSTEM_CLASSES } from "../domain/classes";

export function ClassSelect({
  value,
  onChange,
  disabled,
  id,
}: {
  value: ClassId | "";
  onChange: (value: ClassId | "") => void;
  disabled?: boolean;
  id?: string;
}) {
  const handle = (event: ChangeEvent<HTMLSelectElement>) => {
    const next = event.target.value;
    onChange(next === "" ? "" : (next as ClassId));
  };
  return (
    <select
      id={id}
      value={value}
      onChange={handle}
      disabled={disabled}
      data-testid="class-select"
    >
      <option value="">クラスを選ぶ</option>
      {SYSTEM_CLASSES.map((item) => (
        <option key={item.classId} value={item.classId}>
          {item.displayOrder}. {item.displayName}
        </option>
      ))}
    </select>
  );
}
