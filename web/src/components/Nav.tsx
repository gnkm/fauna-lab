import { Link } from "../router/Link";
import { NAV_ITEMS } from "../router/nav";

export function Nav() {
  return (
    <nav className="nav" aria-label="メイン">
      <ul>
        {NAV_ITEMS.map((item) => (
          <li key={item.to}>
            <Link to={item.to}>{item.label}</Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
