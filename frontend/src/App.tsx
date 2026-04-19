import { NavLink, Route, Routes } from "react-router-dom";
import Watchlist from "./pages/Watchlist";
import TickerDetail from "./pages/TickerDetail";
import Briefing from "./pages/Briefing";

export default function App() {
  return (
    <>
      <nav className="topnav">
        <span className="brand">SFE</span>
        <NavLink
          to="/"
          end
          className={({ isActive }) =>
            isActive ? "navlink active" : "navlink"
          }
        >
          Watchlist
        </NavLink>
        <NavLink
          to="/briefing"
          className={({ isActive }) =>
            isActive ? "navlink active" : "navlink"
          }
        >
          Briefing
        </NavLink>
      </nav>
      <main>
        <Routes>
          <Route path="/" element={<Watchlist />} />
          <Route path="/tickers/:symbol" element={<TickerDetail />} />
          <Route path="/briefing" element={<Briefing />} />
          <Route path="/briefing/:date" element={<Briefing />} />
          <Route path="*" element={<p className="muted">Not found.</p>} />
        </Routes>
      </main>
    </>
  );
}
