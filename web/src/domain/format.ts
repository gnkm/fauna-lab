export function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

export function formatDateTime(value: string): string {
  if (value === "") {
    return "—";
  }
  return value.endsWith("Z")
    ? value.replace("T", " ").replace("Z", " UTC")
    : value;
}
