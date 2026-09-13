import { type ReactNode, useEffect } from "react";
import { AnnotatePage } from "../pages/AnnotatePage";
import { ImageDetailPage } from "../pages/ImageDetailPage";
import { ImagesPage } from "../pages/ImagesPage";
import { InferPage } from "../pages/InferPage";
import { ModelsPage } from "../pages/ModelsPage";
import { NotFoundPage } from "../pages/NotFoundPage";
import { OverviewPage } from "../pages/OverviewPage";
import { SplitsPage } from "../pages/SplitsPage";
import { TrainJobPage } from "../pages/TrainJobPage";
import { TrainPage } from "../pages/TrainPage";
import { PAGE_TITLES, type PageId } from "../router/match";
import { useRouter } from "../router/Router";
import { Nav } from "./Nav";

const PAGE_RENDERERS: Record<PageId, () => ReactNode> = {
  overview: () => <OverviewPage />,
  images: () => <ImagesPage />,
  "image-detail": () => <ImageDetailPage />,
  annotate: () => <AnnotatePage />,
  splits: () => <SplitsPage />,
  train: () => <TrainPage />,
  "train-job": () => <TrainJobPage />,
  models: () => <ModelsPage />,
  infer: () => <InferPage />,
  "not-found": () => <NotFoundPage />,
};

export function Layout() {
  const { match } = useRouter();
  const title = PAGE_TITLES[match.id];

  useEffect(() => {
    document.title = `FaunaLab — ${title}`;
  }, [title]);

  return (
    <div className="shell">
      <a className="skip-link" href="#main">
        本文へスキップ
      </a>
      <header className="masthead">
        <p className="brand">FaunaLab</p>
        <Nav />
      </header>
      <main id="main" key={match.path}>
        {PAGE_RENDERERS[match.id]()}
      </main>
    </div>
  );
}
