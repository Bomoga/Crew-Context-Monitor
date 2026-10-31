import { NavLink, Outlet } from "react-router";
import { useStatusContext } from "../hooks/StatusContext";
import { Banner } from "./Banner";

export const FOOTER_TEXT = "Decision-support prototype, not a medical device";

const NAV = [
  { to: "/", label: "Home", end: true },
  { to: "/history", label: "History" },
  { to: "/events", label: "Events" },
  { to: "/settings", label: "Settings" },
];

/** The shell around every route: title, navigation, banner slot, content, and the footer. */
export function Layout() {
  const polled = useStatusContext();
  return (
    <div className="mx-auto flex min-h-screen max-w-[1280px] flex-col px-4 sm:px-6">
      <header className="flex flex-wrap items-center justify-between gap-3 py-4">
        <p className="text-lg font-bold tracking-tight">Crew Context Monitor</p>
        <nav aria-label="Main" className="flex gap-1">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `rounded-md px-3 py-2 text-sm font-medium ${
                  isActive ? "bg-panel text-ink underline underline-offset-4" : "text-muted"
                } hover:bg-panel`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </header>
      <Banner polled={polled} />
      <main className="flex-1 py-4">
        <Outlet />
      </main>
      <footer className="border-t border-line py-4 text-center text-sm text-muted">
        {FOOTER_TEXT}
      </footer>
    </div>
  );
}
