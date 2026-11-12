import { useEffect, useState } from "react";
import { Link, NavLink, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./auth/AuthProvider";
import { CompassMark, Wordmark } from "./components/Brand";
import History from "./pages/History";
import JustificationForm from "./pages/JustificationForm";
import MigrationPlanPage from "./pages/MigrationPlan";
import Home from "./pages/Home";
import Intake from "./pages/Intake";
import RequestDetail from "./pages/RequestDetail";
import Requests from "./pages/Requests";
import Results from "./pages/Results";

const NAV_ITEMS = [
  { to: "/", label: "Home" },
  { to: "/assessments/new", label: "New assessment" },
  { to: "/migrations/new", label: "Migration plan" },
  { to: "/requests", label: "Requests" },
  { to: "/history", label: "History" },
];

function SignInScreen() {
  const { signIn } = useAuth();
  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-teal-800 px-4">
      <div className="pointer-events-none absolute -left-24 -top-24 h-96 w-96 rounded-full bg-coral-500/30 blur-3xl animate-float" />
      <div className="pointer-events-none absolute -bottom-32 -right-16 h-[28rem] w-[28rem] rounded-full bg-sand-300/25 blur-3xl animate-float [animation-delay:2s]" />
      <div className="relative w-full max-w-sm animate-fade-up rounded-3xl border border-white/10 bg-white/10 p-8 text-center shadow-lift backdrop-blur-xl">
        <CompassMark className="mx-auto h-16 w-16 animate-float" />
        <h1 className="mt-4 font-display text-2xl font-bold text-snow">
          DB<span className="text-coral-400">Compass</span>
        </h1>
        <p className="mt-2 text-sm text-sand-200">Choose the right database, cloud and migration path for your application.</p>
        <button onClick={signIn} className="btn-primary mt-6 w-full py-2.5">
          Sign in with Microsoft
        </button>
      </div>
    </div>
  );
}

function NavItems({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <>
      {NAV_ITEMS.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.to === "/"}
          onClick={onNavigate}
          className={({ isActive }) =>
            `group relative rounded-lg px-3 py-1.5 text-sm font-medium transition ${
              isActive ? "text-snow" : "text-teal-100/75 hover:bg-white/5 hover:text-snow"
            }`
          }
        >
          {({ isActive }) => (
            <>
              {item.label}
              <span
                className={`absolute inset-x-3 -bottom-0.5 h-0.5 origin-left rounded-full bg-coral-500 transition-transform duration-300 ${
                  isActive ? "scale-x-100" : "scale-x-0 group-hover:scale-x-50"
                }`}
              />
            </>
          )}
        </NavLink>
      ))}
    </>
  );
}

function Header() {
  const { mode } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header
      className={`sticky top-0 z-40 border-b border-white/5 transition-all duration-300 ${
        scrolled ? "bg-teal-800/90 shadow-lift backdrop-blur-lg" : "bg-teal-800"
      }`}
    >
      <div className="mx-auto flex max-w-6xl items-center gap-6 px-4 py-3">
        <Link to="/" className="group flex items-center gap-2">
          <CompassMark className="h-8 w-8 transition-transform duration-500 group-hover:rotate-[30deg]" />
          <Wordmark light />
        </Link>
        <nav className="hidden flex-1 items-center gap-1 lg:flex">
          <NavItems />
        </nav>
        {mode === "dev_bypass" && (
          <span className="ml-auto hidden rounded-full border border-gold-300/40 bg-gold-300/15 px-2.5 py-0.5 text-xs font-semibold text-gold-200 lg:inline">
            Dev auth bypass
          </span>
        )}
        <button
          type="button"
          className="ml-auto rounded-lg p-2 text-snow hover:bg-white/10 lg:hidden"
          aria-label="Toggle navigation"
          aria-expanded={menuOpen}
          onClick={() => setMenuOpen(!menuOpen)}
        >
          <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            {menuOpen ? <path d="M6 6l12 12M18 6L6 18" /> : <path d="M4 7h16M4 12h16M4 17h16" />}
          </svg>
        </button>
      </div>
      {menuOpen && (
        <nav className="flex animate-fade-up flex-col gap-1 border-t border-white/10 px-4 py-3 lg:hidden">
          <NavItems onNavigate={() => setMenuOpen(false)} />
        </nav>
      )}
    </header>
  );
}

function Footer() {
  return (
    <footer className="mt-16 border-t border-sand-200/70">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-6 text-xs text-slate-500">
        <span className="flex items-center gap-2">
          <CompassMark className="h-5 w-5" /> DBCompass · internal database advisory portal
        </span>
        <span>AWS · Google Cloud · Azure</span>
      </div>
    </footer>
  );
}

export default function App() {
  const { isAuthenticated } = useAuth();
  const location = useLocation();

  useEffect(() => {
    window.scrollTo({ top: 0 });
  }, [location.pathname]);

  if (!isAuthenticated) {
    return <SignInScreen />;
  }

  const isHome = location.pathname === "/";

  return (
    <div className="flex min-h-screen flex-col">
      <Header />
      <main className={isHome ? "flex-1" : "mx-auto w-full max-w-6xl flex-1 px-4 py-8"}>
        <div key={location.pathname} className="animate-fade-up">
          <Routes location={location}>
            <Route path="/" element={<Home />} />
            <Route path="/assessments/new" element={<Intake />} />
            <Route path="/migrations/new" element={<MigrationPlanPage />} />
            <Route path="/migrations/:id" element={<MigrationPlanPage />} />
            <Route path="/requests" element={<Requests />} />
            <Route path="/requests/new" element={<JustificationForm />} />
            <Route path="/requests/:id" element={<RequestDetail />} />
            <Route path="/requests/:id/edit" element={<JustificationForm />} />
            <Route path="/assessments/:id" element={<Results />} />
            <Route path="/history" element={<History />} />
          </Routes>
        </div>
      </main>
      <Footer />
    </div>
  );
}
