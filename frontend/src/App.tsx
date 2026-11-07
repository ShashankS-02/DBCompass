import { NavLink, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth/AuthProvider";
import Home from "./pages/Home";
import NewAssessment from "./pages/NewAssessment";
import Placeholder from "./pages/Placeholder";

const NAV_ITEMS = [
  { to: "/", label: "Home" },
  { to: "/assessments/new", label: "New assessment" },
  { to: "/repo", label: "Analyze repo" },
  { to: "/migrations/new", label: "Migration plan" },
  { to: "/history", label: "History" },
];

function SignInScreen() {
  const { signIn } = useAuth();
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50">
      <button
        onClick={signIn}
        className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700"
      >
        Sign in with Microsoft
      </button>
    </div>
  );
}

export default function App() {
  const { isAuthenticated, mode } = useAuth();

  if (!isAuthenticated) {
    return <SignInScreen />;
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
          <span className="font-semibold text-slate-900">DBCompass</span>
          <nav className="flex flex-wrap gap-4">
            {NAV_ITEMS.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end
                className={({ isActive }) =>
                  `text-sm ${isActive ? "font-medium text-slate-900" : "text-slate-500 hover:text-slate-800"}`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
          {mode === "dev_bypass" && (
            <span className="ml-auto rounded bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800">
              Dev auth bypass
            </span>
          )}
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 py-8">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/assessments/new" element={<NewAssessment />} />
          <Route path="/repo" element={<Placeholder title="Analyze repo" milestone="M5" />} />
          <Route path="/migrations/new" element={<Placeholder title="Migration plan" milestone="M6" />} />
          <Route path="/history" element={<Placeholder title="History" milestone="M3" />} />
        </Routes>
      </main>
    </div>
  );
}
