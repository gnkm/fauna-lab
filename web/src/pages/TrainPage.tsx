import { EmptyState } from "../components/EmptyState";
import { Link } from "../router/Link";

export function TrainPage() {
  return (
    <article className="page">
      <h1>学習</h1>
      <EmptyState title="学習ジョブはありません">
        <p>
          学習の開始、進捗、ログ、中止はこの画面で行います。同時に実行できる学習は
          1 件です。
        </p>
        <p>
          ラベル付き画像を<Link to="/splits">分割</Link>
          したあとで開始できます。中止は取り消しできないため、実行前に確認ダイアログを出します。
        </p>
      </EmptyState>
    </article>
  );
}
