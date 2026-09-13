import { EmptyState } from "../components/EmptyState";
import { Link } from "../router/Link";

export function NotFoundPage() {
  return (
    <article className="page">
      <h1>画面が見つかりません</h1>
      <EmptyState title="この URL の画面はありません">
        <p>
          アドレスが違うか、古いリンクです。上のナビから機能を選ぶか、
          <Link to="/">概況</Link>へ戻ってください。
        </p>
      </EmptyState>
    </article>
  );
}
