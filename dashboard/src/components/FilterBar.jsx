import { FILTER_GROUPS } from "../utils/filters";

function TogglePill({ label, active, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`toggle-pill ${active ? "toggle-pill-on" : "toggle-pill-off"}`}
    >
      {label}
    </button>
  );
}

export default function FilterBar({ filters, setFilters }) {
  const toggle = (key) =>
    setFilters((f) => ({ ...f, [key]: !f[key] }));

  return (
    <div className="space-y-4">
      {FILTER_GROUPS.map((group) => (
        <div key={group.title}>
          <p className="text-[10px] uppercase tracking-widest text-muted font-semibold mb-2">
            {group.title}
          </p>
          <div className="flex flex-wrap gap-2">
            {group.items.map((item) => (
              <TogglePill
                key={item.key}
                label={item.label}
                active={filters[item.key]}
                onClick={() => toggle(item.key)}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
