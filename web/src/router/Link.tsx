import type { MouseEvent, ReactNode } from "react";
import { useRouter } from "./Router";

export function Link({
  to,
  children,
  className,
}: {
  to: string;
  children: ReactNode;
  className?: string;
}) {
  const { path, navigate } = useRouter();
  const current =
    to === "/" ? path === "/" : path === to || path.startsWith(`${to}/`);

  const onClick = (event: MouseEvent<HTMLAnchorElement>) => {
    if (
      event.defaultPrevented ||
      event.button !== 0 ||
      event.metaKey ||
      event.altKey ||
      event.ctrlKey ||
      event.shiftKey
    ) {
      return;
    }
    event.preventDefault();
    navigate(to);
  };

  return (
    <a
      href={to}
      className={className}
      aria-current={current ? "page" : undefined}
      onClick={onClick}
    >
      {children}
    </a>
  );
}
