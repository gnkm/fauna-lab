import { displayNameFor } from "../domain/classes";
import { formatPercent } from "../domain/format";
import type { ModelMetrics } from "../domain/models";

export function ConfusionMatrixTable({ metrics }: { metrics: ModelMetrics }) {
  const labels = metrics.confusion_matrix.labels;
  const matrix = metrics.confusion_matrix.matrix;
  return (
    <section aria-labelledby="matrix-heading">
      <h2 id="matrix-heading">混同行列</h2>
      <p className="muted">行が正解クラス、列が予測クラスです。</p>
      <div className="matrix-wrap">
        <table className="matrix" data-testid="confusion-matrix">
          <caption>混同行列（正解 × 予測）</caption>
          <thead>
            <tr>
              <th scope="col">正解＼予測</th>
              {labels.map((label) => (
                <th key={label} scope="col">
                  {displayNameFor(label)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {labels.map((rowLabel, rowIndex) => (
              <tr key={rowLabel}>
                <th scope="row">{displayNameFor(rowLabel)}</th>
                {(matrix[rowIndex] ?? []).map((cell, colIndex) => (
                  <td
                    key={`${rowLabel}-${labels[colIndex] ?? String(colIndex)}`}
                  >
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <h2>クラス別指標</h2>
      <table data-testid="per-class-metrics">
        <caption>precision / recall / F1</caption>
        <thead>
          <tr>
            <th scope="col">クラス</th>
            <th scope="col">Precision</th>
            <th scope="col">Recall</th>
            <th scope="col">F1</th>
            <th scope="col">件数</th>
          </tr>
        </thead>
        <tbody>
          {labels.map((label) => {
            const metric = metrics.per_class[label];
            return (
              <tr key={label}>
                <th scope="row">{displayNameFor(label)}</th>
                <td>
                  {metric === undefined ? "—" : formatPercent(metric.precision)}
                </td>
                <td>
                  {metric === undefined ? "—" : formatPercent(metric.recall)}
                </td>
                <td>{metric === undefined ? "—" : formatPercent(metric.f1)}</td>
                <td>{metric === undefined ? "—" : String(metric.support)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}
