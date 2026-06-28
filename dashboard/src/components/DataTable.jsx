import { formatWoundType, routingBadgeClass, dimsRow } from "../utils/format";

const COLUMNS = [
  { key: "patient_id", label: "ID", w: "w-24" },
  { key: "name", label: "Name", w: "w-36" },
  { key: "facility", label: "Facility", w: "w-28" },
  { key: "routing", label: "Routing", w: "w-32" },
  { key: "wound_type", label: "Type", w: "w-28" },
  { key: "stage", label: "Stage", w: "w-20" },
  { key: "location", label: "Location", w: "w-36" },
  { key: "dims", label: "L × W × D", w: "w-28 mono" },
  { key: "drainage_amount", label: "Drainage", w: "w-24" },
  { key: "has_medicare_b", label: "MCB", w: "w-16" },
  { key: "has_wound_dx", label: "Dx", w: "w-16" },
  { key: "extraction_source", label: "Source", w: "w-24" },
  { key: "reason", label: "Reason", w: "min-w-[280px]" },
];

export default function DataTable({ rows, selectedId, onSelect }) {
  return (
    <div className="overflow-auto rounded-xl border border-border bg-panel/80 backdrop-blur-sm max-h-[calc(100vh-220px)]">
      <table className="data-table w-full min-w-[1200px]">
        <thead>
          <tr>
            {COLUMNS.map((col) => (
              <th key={col.key} className={col.w}>
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={COLUMNS.length} className="text-center py-16 text-muted">
                No patients match current filters
              </td>
            </tr>
          ) : (
            rows.map((p) => (
              <tr
                key={p.patient_id}
                className={selectedId === p.patient_id ? "selected cursor-pointer" : "cursor-pointer"}
                onClick={() => onSelect(p)}
              >
                <td className="mono font-medium text-white/90">{p.patient_id}</td>
                <td>{p.name}</td>
                <td className="text-muted text-xs">{p.facility}</td>
                <td>
                  <span
                    className={`inline-block px-2 py-0.5 rounded-md text-xs font-medium border ${routingBadgeClass(p.routing)}`}
                  >
                    {p.routing_label}
                  </span>
                </td>
                <td className="text-xs">{formatWoundType(p.wound_type)}</td>
                <td className="text-xs">{p.stage ?? "—"}</td>
                <td className="text-xs max-w-[160px] truncate" title={p.location}>
                  {p.location ?? "—"}
                </td>
                <td className="mono text-xs">{dimsRow(p)}</td>
                <td className="text-xs capitalize">{p.drainage_amount ?? "—"}</td>
                <td className="text-xs">{p.has_medicare_b ? "✓" : "—"}</td>
                <td className="text-xs">{p.has_wound_dx ? "✓" : "—"}</td>
                <td className="text-xs text-muted">{p.extraction_source ?? "—"}</td>
                <td className="text-xs text-muted max-w-md truncate" title={p.reason}>
                  {p.reason}
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
