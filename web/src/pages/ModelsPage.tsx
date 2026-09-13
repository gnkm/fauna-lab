import { EmptyState } from "../components/EmptyState";
import { Link } from "../router/Link";

export function ModelsPage() {
  return (
    <article className="page">
      <h1>モデル</h1>
      <EmptyState title="操作できるモデル版がまだ並びません">
        <p>
          モデル版の一覧、評価指標、有効化、削除、再評価を行います。ベースライン（版
          0）と学習済モデルを区別して示します。
        </p>
        <p>
          有効モデルが無い場合の典型的な原因は、配布資産が無いこと、または学習済モデルが無く有効化もされていないことです。概況の有効モデル欄も同じ状態を表示します。
        </p>
        <p>
          有効モデルがあれば、<Link to="/infer">推論</Link>
          と候補生成に使われます。削除は実行前に確認します。有効モデルと版 0
          は削除できません。
        </p>
      </EmptyState>
    </article>
  );
}
