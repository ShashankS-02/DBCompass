import { Suspense, lazy, useEffect, useState } from "react";
import { Link, NavLink, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./auth/AuthProvider";
import { CompassMark, DialBackdrop, Wordmark } from "./components/Brand";
import History from "./pages/History";
import JustificationForm from "./pages/JustificationForm";
import MigrationPlanPage from "./pages/MigrationPlan";
import Home from "./pages/Home";
import Intake from "./pages/Intake";
import RequestDetail from "./pages/RequestDetail";
import Requests from "./pages/Requests";
import Results from "./pages/Results";
import { PageLoader } from "./components/Loader";

const Help = lazy(() => import("./pages/Help"));

const NAV_ITEMS = [
  { to: "/", label: "Home" },
  { to: "/assessments/new", label: "New assessment" },
  { to: "/migrations/new", label: "Migration plan" },
  { to: "/requests", label: "Requests" },
  { to: "/history", label: "History" },
];

const MOBILE_ONLY_ITEMS = [{ to: "/help", label: "Help" }];

function SignInScreen() {
  const { signIn } = useAuth();
  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-coral-500 px-4">
      <DialBackdrop />
      <div className="relative w-full max-w-sm animate-fade-up rounded-3xl bg-snow p-8 text-center shadow-lift">
        <CompassMark className="mx-auto h-16 w-16 animate-float" />
        <h1 className="mt-4 font-display text-2xl font-bold text-slate-900">
          DB<span className="text-coral-500">Compass</span>
        </h1>
        <p className="mt-2 text-sm text-slate-600">Choose the right database, cloud and migration path for your application.</p>
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
      {[...NAV_ITEMS, ...(onNavigate ? MOBILE_ONLY_ITEMS : [])].map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.to === "/"}
          onClick={onNavigate}
          className={({ isActive }) =>
            `group relative rounded-lg px-3 py-1.5 text-sm font-medium transition ${
              isActive ? "bg-coral-50 text-coral-700" : "text-slate-600 hover:bg-sand-100 hover:text-slate-900"
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
      className={`sticky top-0 z-40 border-b transition-all duration-300 ${
        scrolled ? "border-sand-200/80 bg-snow/85 shadow-soft backdrop-blur-lg" : "border-transparent bg-snow"
      }`}
    >
      <div className="mx-auto flex max-w-6xl items-center gap-6 px-4 py-3">
        <Link to="/" className="group flex items-center gap-2">
          <CompassMark className="h-8 w-8 transition-transform duration-500 group-hover:rotate-[30deg]" />
          <Wordmark />
        </Link>
        <nav className="hidden flex-1 items-center gap-1 lg:flex">
          <NavItems />
        </nav>
        <NavLink
          to="/help"
          className={({ isActive }) =>
            `ml-auto hidden items-center gap-1.5 rounded-xl border px-3 py-1.5 text-sm font-semibold transition lg:inline-flex ${
              isActive ? "border-coral-500 bg-coral-500 text-white" : "border-coral-200 text-coral-700 hover:bg-coral-50"
            }`
          }
        >
          <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <circle cx="12" cy="12" r="9" />
            <path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6v.6M12 17h.01" />
          </svg>
          Help
        </NavLink>
        {mode === "dev_bypass" && (
          <span className="hidden rounded-full border border-gold-300 bg-gold-50 px-2.5 py-0.5 text-xs font-semibold text-gold-800 lg:inline">
            Dev auth bypass
          </span>
        )}
        <button
          type="button"
          className="ml-auto rounded-lg p-2 text-slate-800 hover:bg-sand-100 lg:hidden"
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
        <nav className="flex animate-fade-up flex-col gap-1 border-t border-sand-200 px-4 py-3 lg:hidden">
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
            <Route path="/help" element={<Suspense fallback={<PageLoader label="Loading Help" steps={["Fetching guides"]} />}><Help /></Suspense>} />
          </Routes>
        </div>
      </main>
      <Footer />
    </div>
  );
}
