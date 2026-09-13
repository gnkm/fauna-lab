import { EmptyState } from "../components/EmptyState";
import { Link } from "../router/Link";

export function ImagesPage() {
  return (
    <article className="page">
      <h1>画像</h1>
      <EmptyState title="登録された画像はまだありません">
        <p>
          JPEG または PNG
          をこの画面から登録できます。複数ファイルを一度に選べます。一部が失敗しても他の登録は続きます。
        </p>
        <p>
          手元に画像が無いときは、<Link to="/">概況</Link>
          の「サンプルデータを投入」から始めてください。
        </p>
      </EmptyState>
    </article>
  );
}
