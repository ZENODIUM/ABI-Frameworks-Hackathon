import DataTable from "../components/DataTable";
import FilterBar from "../components/FilterBar";
import PatientDetailCard from "../components/PatientDetailCard";
import TrafficLights from "../components/TrafficLights";

function StatPill({ label, value }) {
  return (
    <div className="text-center px-4">
      <p className="text-3xl md:text-4xl font-semibold mono text-white/90">{value}</p>
      <p className="text-[10px] uppercase tracking-wider text-muted mt-1">{label}</p>
    </div>
  );
}

export default function DashboardPage({
  patients,
  filtered,
  filters,
  setFilters,
  search,
  setSearch,
  counts,
  filteredCounts,
  selectedPatient,
  onSelectPatient,
  onClosePatient,
}) {
  const showCard = Boolean(selectedPatient);

  return (
    <>
      <div className={`flex gap-6 min-h-0 transition-opacity ${showCard ? "opacity-40 pointer-events-none" : ""}`}>
        <aside className="w-44 shrink-0 pt-2">
          <TrafficLights
            filters={filters}
            onToggle={(key) => setFilters((f) => ({ ...f, [key]: !f[key] }))}
            counts={counts}
            filteredCounts={filteredCounts}
            selectedPatient={null}
          />
        </aside>

        <div className="flex-1 min-w-0 space-y-4">
          <div className="relative">
            <svg
              className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-muted"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search patients, wounds, reasons, IDs…"
              className="w-full pl-11 pr-4 py-3 rounded-xl bg-panel border border-border text-sm placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-white/10"
            />
          </div>

          <div className="flex items-center justify-center gap-8 py-2 rounded-xl border border-border/50 bg-panel/30">
            <StatPill label="Showing" value={filtered.length} />
            <div className="w-px h-10 bg-border" />
            <StatPill label="Total" value={patients.length} />
            <div className="w-px h-10 bg-border" />
            <StatPill label="Accept" value={counts.auto_accept} />
            <StatPill label="Review" value={counts.flag_for_review} />
            <StatPill label="Reject" value={counts.reject} />
          </div>

          <div className="rounded-xl border border-border bg-panel/50 p-4">
            <FilterBar filters={filters} setFilters={setFilters} />
          </div>

          <DataTable
            rows={filtered}
            selectedId={selectedPatient?.patient_id}
            onSelect={onSelectPatient}
          />
        </div>
      </div>

      {showCard && (
        <PatientDetailCard
          patient={selectedPatient}
          counts={counts}
          onClose={onClosePatient}
        />
      )}
    </>
  );
}
