import { EmptyState } from "../components/EmptyState";
import { Link } from "../router/Link";
import { useRouter } from "../router/Router";

export function TrainJobPage() {
  const { match } = useRouter();
  const ref = match.params.ref ?? "";
  return (
    <article className="page">
      <h1>学習ジョブ</h1>
      <EmptyState title="この学習ジョブは表示できません">
        <p>
          識別子 <code>{ref}</code>{" "}
          のジョブが見つからないか、まだ開始されていません。
        </p>
        <p>
          <Link to="/train">学習</Link>
          に戻って、開始済みのジョブを選んでください。
        </p>
      </EmptyState>
    </article>
  );
}
