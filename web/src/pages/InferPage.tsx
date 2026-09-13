import { EmptyState } from "../components/EmptyState";
import { Link } from "../router/Link";

export function InferPage() {
  return (
    <article className="page">
      <h1>推論</h1>
      <EmptyState title="推論履歴はありません">
        <p>
          有効モデルで画像を分類し、結果と履歴を確認します。ベースラインがあれば学習前でも実行できます。
        </p>
        <p>
          有効モデルが無いときは、<Link to="/">概況</Link>
          の原因を確認してください。画像が無いときは
          <Link to="/images">画像</Link>から登録します。
        </p>
      </EmptyState>
    </article>
  );
}
