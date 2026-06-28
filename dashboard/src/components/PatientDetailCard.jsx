import TrafficLights from "./TrafficLights";
import { usePatientSummary } from "../hooks/usePatientSummary";
import { dimsRow, formatWoundType, routingBadgeClass } from "../utils/format";

function DetailCell({ label, value, mono }) {
  return (
    <div className="rounded-xl bg-white/[0.03] border border-border/60 px-4 py-3">
      <p className="text-[10px] uppercase tracking-wider text-muted mb-1">{label}</p>
      <p className={`text-sm text-white/90 ${mono ? "mono" : ""}`}>{value ?? "—"}</p>
    </div>
  );
}

export default function PatientDetailCard({ patient, counts, onClose }) {
  const { summary, loading, error } = usePatientSummary(patient);

  if (!patient) return null;

  return (
    <div className="fixed inset-0 z-30 flex items-center justify-center p-4 md:p-8 bg-black/60 backdrop-blur-sm">
      <div
        className="relative w-full max-w-5xl max-h-[92vh] overflow-y-auto rounded-2xl border border-border/80 bg-panel shadow-2xl"
        style={{
          background: "linear-gradient(165deg, #1e2a3d 0%, #141c28 45%, #0f1419 100%)",
        }}
      >
        {/* Close */}
        <button
          type="button"
          onClick={onClose}
          className="absolute top-4 right-4 z-10 w-9 h-9 rounded-full bg-white/5 border border-border hover:bg-white/10 flex items-center justify-center text-muted hover:text-white transition-colors"
          aria-label="Close"
        >
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>

        <div className="p-6 md:p-10 space-y-8">
          {/* Header + traffic lights */}
          <div className="flex flex-col items-center text-center border-b border-border/50 pb-8">
            <TrafficLights
              focusMode
              selectedPatient={patient}
              counts={counts}
              filteredCounts={{ auto_accept: 0, flag_for_review: 0, reject: 0 }}
              filters={{}}
              layout="horizontal"
              size="lg"
            />
            <h2 className="text-2xl md:text-3xl font-bold mt-6 tracking-tight">
              {patient.patient_id}
            </h2>
            <p className="text-lg text-white/70 mt-1">{patient.name}</p>
            <p className="text-sm text-muted mt-1">{patient.facility}</p>
            <span
              className={`inline-block mt-4 px-4 py-1.5 rounded-full text-sm font-medium border ${routingBadgeClass(patient.routing)}`}
            >
              {patient.routing_label}
            </span>
          </div>

          {/* Wound & billing grid */}
          <div>
            <h3 className="text-xs uppercase tracking-widest text-muted font-semibold mb-4">
              Wound & Billing Data
            </h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <DetailCell label="Wound Type" value={formatWoundType(patient.wound_type)} />
              <DetailCell label="Stage" value={patient.stage} />
              <DetailCell label="Location" value={patient.location} />
              <DetailCell label="Drainage" value={patient.drainage_amount} />
              <DetailCell label="Length" value={patient.length_cm ? `${patient.length_cm} cm` : null} mono />
              <DetailCell label="Width" value={patient.width_cm ? `${patient.width_cm} cm` : null} mono />
              <DetailCell label="Depth" value={patient.depth_cm ? `${patient.depth_cm} cm` : null} mono />
              <DetailCell label="L × W × D" value={dimsRow(patient)} mono />
            </div>
          </div>

          {/* Insurance & extraction */}
          <div>
            <h3 className="text-xs uppercase tracking-widest text-muted font-semibold mb-4">
              Eligibility & Extraction
            </h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <DetailCell label="Primary Payer" value={patient.primary_payer} />
              <DetailCell label="Medicare Part B" value={patient.has_medicare_b ? "Active" : "No"} />
              <DetailCell label="Wound Diagnosis" value={patient.has_wound_dx ? "Yes" : "No"} />
              <DetailCell label="ICD-10" value={patient.wound_dx_codes} mono />
              <DetailCell label="Data Source" value={patient.extraction_source} />
              <DetailCell label="Gemini Assisted" value={patient.used_llm ? "Yes" : "No"} />
              <DetailCell
                label="Missing Fields"
                value={(patient.missing_fields || []).join(", ") || "None"}
              />
              <DetailCell
                label="Ambiguity Flags"
                value={patient.ambiguity_flags || "None"}
              />
            </div>
          </div>

          {/* Decision reason */}
          <div className="rounded-xl bg-white/[0.02] border border-border/50 p-5">
            <h3 className="text-xs uppercase tracking-widest text-muted font-semibold mb-2">
              Routing Decision
            </h3>
            <p className="text-sm text-white/80 leading-relaxed">{patient.reason}</p>
          </div>

          {/* AI Summary */}
          <div
            className="rounded-xl border p-5"
            style={{
              borderColor: "rgba(147, 197, 253, 0.2)",
              background: "linear-gradient(135deg, rgba(59,130,246,0.08) 0%, rgba(99,102,241,0.05) 100%)",
            }}
          >
            <div className="flex items-center gap-2 mb-3">
              <div className="w-7 h-7 rounded-lg bg-blue-500/20 flex items-center justify-center">
                <svg className="w-4 h-4 text-blue-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                </svg>
              </div>
              <h3 className="text-sm font-semibold text-blue-200/90">AI Summary</h3>
              <span className="text-[10px] text-muted ml-auto">Gemini 2.5 Flash Lite</span>
            </div>
            {loading && (
              <div className="flex items-center gap-2 text-sm text-muted py-4">
                <div className="w-4 h-4 border-2 border-blue-400/30 border-t-blue-400 rounded-full animate-spin" />
                Generating biller summary…
              </div>
            )}
            {error && (
              <p className="text-sm text-soft-reject/90 py-2">
                {error}
                <span className="block text-xs text-muted mt-1">
                  Start API: python dashboard_api.py (set GEMINI_API_KEY)
                </span>
              </p>
            )}
            {summary && !loading && (
              <p className="text-sm text-white/85 leading-relaxed">{summary}</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
