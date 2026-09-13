import { EmptyState } from "../components/EmptyState";
import { Link } from "../router/Link";

export function AnnotatePage() {
  return (
    <article className="page">
      <h1>アノテーション</h1>
      <EmptyState title="ラベルを付ける画像がありません">
        <p>
          未ラベル画像に対して、確定ラベルの付与・一括付与・解除と、候補ラベルの生成・採用・却下を行います。犬種の目視分類は前提にしません。
        </p>
        <p>
          先に<Link to="/images">画像</Link>を登録するか、
          <Link to="/">概況</Link>
          からサンプルを投入してください。候補の生成には有効モデルが必要です。
        </p>
      </EmptyState>
    </article>
  );
}
