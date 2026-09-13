import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { type Match, matchPath, normalizePath } from "./match";

type RouterValue = {
  match: Match;
  path: string;
  navigate: (to: string) => void;
};

const RouterContext = createContext<RouterValue | null>(null);

export function RouterProvider({ children }: { children: ReactNode }) {
  const [path, setPath] = useState(() =>
    normalizePath(window.location.pathname),
  );

  useEffect(() => {
    const onPop = () => {
      setPath(normalizePath(window.location.pathname));
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const navigate = useCallback((to: string) => {
    const next = normalizePath(to);
    if (next === normalizePath(window.location.pathname)) {
      return;
    }
    window.history.pushState(null, "", next);
    setPath(next);
  }, []);

  const match = useMemo(() => matchPath(path), [path]);
  const value = useMemo(
    () => ({ match, path, navigate }),
    [match, path, navigate],
  );

  return (
    <RouterContext.Provider value={value}>{children}</RouterContext.Provider>
  );
}

export function useRouter(): RouterValue {
  const value = useContext(RouterContext);
  if (value === null) {
    throw new Error("RouterProvider がありません");
  }
  return value;
}
