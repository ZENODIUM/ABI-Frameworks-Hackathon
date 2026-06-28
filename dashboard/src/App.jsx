import { useEffect, useMemo, useState } from "react";
import AnalyticsPage from "./pages/AnalyticsPage";
import DashboardPage from "./pages/DashboardPage";
import { applyFilters, countByRouting, DEFAULT_FILTERS } from "./utils/filters";

export default function App() {
  const [patients, setPatients] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [page, setPage] = useState("dashboard");
  const [filters, setFilters] = useState(DEFAULT_FILTERS);
  const [savedFilters, setSavedFilters] = useState(null);
  const [search, setSearch] = useState("");
  const [selectedPatient, setSelectedPatient] = useState(null);

  useEffect(() => {
    fetch("/patients.json")
      .then((r) => {
        if (!r.ok) throw new Error("patients.json not found — run: python export_dashboard_data.py");
        return r.json();
      })
      .then((data) => {
        setPatients(data);
        setLoading(false);
      })
      .catch((e) => {
        setError(e.message);
        setLoading(false);
      });
  }, []);

  const counts = useMemo(() => countByRouting(patients), [patients]);

  const filtered = useMemo(
    () => applyFilters(patients, filters, search, selectedPatient?.patient_id),
    [patients, filters, search, selectedPatient]
  );

  const filteredCounts = useMemo(() => countByRouting(filtered), [filtered]);

  const handleSelectPatient = (patient) => {
    setSelectedPatient(patient);
    setSavedFilters(filters);
    setFilters((f) => ({
      ...f,
      showAutoAccept: patient.routing === "auto_accept",
      showFlag: patient.routing === "flag_for_review",
      showReject: patient.routing === "reject",
    }));
  };

  const handleClosePatient = () => {
    setSelectedPatient(null);
    if (savedFilters) {
      setFilters(savedFilters);
      setSavedFilters(null);
    } else {
      setFilters((f) => ({
        ...f,
        showAutoAccept: true,
        showFlag: true,
        showReject: true,
      }));
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center text-muted">
        Loading patient data…
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center p-8">
        <div className="max-w-md text-center rounded-xl border border-soft-reject/30 bg-panel p-8">
          <p className="text-soft-reject font-medium mb-2">Data not loaded</p>
          <p className="text-sm text-muted">{error}</p>
          <code className="block mt-4 text-xs bg-black/30 rounded p-3 mono">
            python export_dashboard_data.py
            <br />
            cd dashboard && npm run dev
          </code>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b border-border/60 bg-panel/50 backdrop-blur-md sticky top-0 z-20">
        <div className="max-w-[1600px] mx-auto px-6 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold tracking-tight">Wound Route</h1>
            <p className="text-xs text-muted mt-0.5">
              Medicare Part B wound billing · {patients.length} patients
            </p>
          </div>
          <nav className="flex gap-1 p-1 rounded-lg bg-black/15 border border-border/60">
            {[
              { id: "dashboard", label: "Patients" },
              { id: "analytics", label: "Analytics" },
            ].map((tab) => (
              <button
                key={tab.id}
                type="button"
                onClick={() => {
                  setPage(tab.id);
                  if (tab.id === "analytics") handleClosePatient();
                }}
                className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                  page === tab.id
                    ? "bg-white/10 text-white"
                    : "text-muted hover:text-white/80"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </nav>
        </div>
      </header>

      <main className="flex-1 max-w-[1600px] w-full mx-auto px-6 py-6">
        {page === "dashboard" ? (
          <DashboardPage
            patients={patients}
            filtered={filtered}
            filters={filters}
            setFilters={setFilters}
            search={search}
            setSearch={setSearch}
            counts={counts}
            filteredCounts={filteredCounts}
            selectedPatient={selectedPatient}
            onSelectPatient={handleSelectPatient}
            onClosePatient={handleClosePatient}
          />
        ) : (
          <AnalyticsPage patients={patients} />
        )}
      </main>
    </div>
  );
}
