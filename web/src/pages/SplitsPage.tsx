import { EmptyState } from "../components/EmptyState";
import { Link } from "../router/Link";

export function SplitsPage() {
  return (
    <article className="page">
      <h1>分割</h1>
      <EmptyState title="分割できるラベル付き画像がありません">
        <p>
          確定ラベル付き画像を訓練・検証・試験へ層化分割します。未ラベルは未割当のままです。
        </p>
        <p>
          先に<Link to="/annotate">アノテーション</Link>
          で確定ラベルを付けてから、この画面で分割してください。
        </p>
      </EmptyState>
    </article>
  );
}
