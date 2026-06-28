import PipelineMindmap from "../components/PipelineMindmap";
import {
  Bar,
  BarChart,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const SOFT = {
  accept: "#86efac",
  acceptMuted: "rgba(134, 239, 172, 0.35)",
  flag: "#fde68a",
  flagMuted: "rgba(253, 230, 138, 0.35)",
  reject: "#fca5a5",
  rejectMuted: "rgba(252, 165, 165, 0.35)",
  blue: "#93c5fd",
  purple: "#c4b5fd",
};

const ROUTING_COLORS = {
  "Auto Accept": SOFT.accept,
  "Flag for Review": SOFT.flag,
  Reject: SOFT.reject,
};

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-panel/95 border border-border/60 rounded-xl px-4 py-2.5 text-sm shadow-lg backdrop-blur">
      <p className="font-medium text-white/90">{label || payload[0].name}</p>
      <p className="text-muted text-xs mt-0.5">{payload[0].value} patients</p>
    </div>
  );
};

function BigStat({ label, value, accent }) {
  return (
    <div className="rounded-2xl border border-border/50 bg-panel/40 p-6 text-center">
      <p
        className="text-5xl md:text-6xl font-semibold mono tracking-tight"
        style={{ color: accent || "#f1f5f9" }}
      >
        {value}
      </p>
      <p className="text-xs uppercase tracking-widest text-muted mt-3 font-medium">{label}</p>
    </div>
  );
}

export default function AnalyticsPage({ patients }) {
  const routingData = [
    { name: "Auto Accept", value: patients.filter((p) => p.routing === "auto_accept").length },
    { name: "Flag for Review", value: patients.filter((p) => p.routing === "flag_for_review").length },
    { name: "Reject", value: patients.filter((p) => p.routing === "reject").length },
  ];

  const facilityData = ["Facility A", "Facility B", "Facility C"].map((fac) => {
    const subset = patients.filter((p) => p.facility === fac);
    return {
      facility: fac.replace("Facility ", "F"),
      accept: subset.filter((p) => p.routing === "auto_accept").length,
      flag: subset.filter((p) => p.routing === "flag_for_review").length,
      reject: subset.filter((p) => p.routing === "reject").length,
    };
  });

  const rejectBreakdown = [
    { name: "No Medicare B", value: patients.filter((p) => p.reject_category === "no_medicare_b").length },
    { name: "Resolved dx", value: patients.filter((p) => p.reject_category === "resolved_diagnosis").length },
    { name: "No evidence", value: patients.filter((p) => p.reject_category === "no_wound_evidence").length },
  ].filter((d) => d.value > 0);

  const flagBreakdown = [
    { name: "Missing depth", value: patients.filter((p) => (p.missing_fields || []).some((f) => f.includes("depth"))).length },
    { name: "Missing stage", value: patients.filter((p) => (p.missing_fields || []).some((f) => f.includes("stage"))).length },
    { name: "Missing location", value: patients.filter((p) => (p.missing_fields || []).some((f) => f.includes("location"))).length },
    { name: "Ambiguity", value: patients.filter((p) => p.has_ambiguity).length },
  ].filter((d) => d.value > 0);

  const extractionData = [
    { name: "Assess + Notes", value: patients.filter((p) => p.extraction_source === "both").length, color: SOFT.purple },
    { name: "Assess only", value: patients.filter((p) => p.extraction_source === "assessment").length, color: SOFT.blue },
    { name: "Notes only", value: patients.filter((p) => p.extraction_source === "notes").length, color: SOFT.flag },
    { name: "Gemini-assisted", value: patients.filter((p) => p.used_llm).length, color: "#a5b4fc" },
  ].filter((d) => d.value > 0);

  const mcb = patients.filter((p) => p.has_medicare_b).length;

  return (
    <div className="space-y-8">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <BigStat label="Total patients" value={patients.length} />
        <BigStat label="Medicare B" value={mcb} accent={SOFT.blue} />
        <BigStat label="Ready to bill" value={routingData[0].value} accent={SOFT.accept} />
        <BigStat label="Needs review" value={routingData[1].value} accent={SOFT.flag} />
      </div>

      <PipelineMindmap patients={patients} />

      <div className="grid md:grid-cols-2 gap-6">
        <div className="rounded-2xl border border-border/50 bg-panel/30 p-6">
          <h3 className="text-sm font-medium text-white/70 mb-5">Routing distribution</h3>
          <ResponsiveContainer width="100%" height={240}>
            <PieChart>
              <Pie
                data={routingData}
                dataKey="value"
                nameKey="name"
                cx="50%"
                cy="50%"
                innerRadius={60}
                outerRadius={90}
                paddingAngle={4}
                stroke="none"
              >
                {routingData.map((entry) => (
                  <Cell key={entry.name} fill={ROUTING_COLORS[entry.name]} fillOpacity={0.75} />
                ))}
              </Pie>
              <Tooltip content={<CustomTooltip />} />
            </PieChart>
          </ResponsiveContainer>
          <div className="flex justify-center gap-5 mt-3 text-xs text-muted">
            {routingData.map((d) => (
              <span key={d.name} className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full opacity-70" style={{ background: ROUTING_COLORS[d.name] }} />
                {d.name} <strong className="text-white/80 mono">{d.value}</strong>
              </span>
            ))}
          </div>
        </div>

        <div className="rounded-2xl border border-border/50 bg-panel/30 p-6">
          <h3 className="text-sm font-medium text-white/70 mb-5">By facility</h3>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={facilityData} barGap={3}>
              <XAxis dataKey="facility" tick={{ fill: "#94a3b8", fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} axisLine={false} tickLine={false} />
              <Tooltip content={<CustomTooltip />} />
              <Bar dataKey="accept" stackId="a" fill={SOFT.accept} fillOpacity={0.7} radius={[0, 0, 0, 0]} />
              <Bar dataKey="flag" stackId="a" fill={SOFT.flag} fillOpacity={0.7} />
              <Bar dataKey="reject" stackId="a" fill={SOFT.reject} fillOpacity={0.7} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {rejectBreakdown.length > 0 && (
          <div className="rounded-2xl border border-border/50 bg-panel/30 p-6">
            <h3 className="text-sm font-medium text-white/70 mb-5">Reject reasons</h3>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={rejectBreakdown} layout="vertical" margin={{ left: 8 }}>
                <XAxis type="number" hide />
                <YAxis type="category" dataKey="name" width={95} tick={{ fill: "#94a3b8", fontSize: 11 }} axisLine={false} tickLine={false} />
                <Tooltip content={<CustomTooltip />} />
                <Bar dataKey="value" fill={SOFT.reject} fillOpacity={0.65} radius={[0, 6, 6, 0]} barSize={20} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}

        {flagBreakdown.length > 0 && (
          <div className="rounded-2xl border border-border/50 bg-panel/30 p-6">
            <h3 className="text-sm font-medium text-white/70 mb-5">Review triggers</h3>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={flagBreakdown} layout="vertical" margin={{ left: 8 }}>
                <XAxis type="number" hide />
                <YAxis type="category" dataKey="name" width={95} tick={{ fill: "#94a3b8", fontSize: 11 }} axisLine={false} tickLine={false} />
                <Tooltip content={<CustomTooltip />} />
                <Bar dataKey="value" fill={SOFT.flag} fillOpacity={0.65} radius={[0, 6, 6, 0]} barSize={20} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      <div className="rounded-2xl border border-border/50 bg-panel/30 p-6">
        <h3 className="text-sm font-medium text-white/70 mb-6">Extraction sources</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
          {extractionData.map((d) => (
            <div key={d.name} className="text-center">
              <p className="text-4xl font-semibold mono" style={{ color: d.color }}>{d.value}</p>
              <p className="text-xs text-muted mt-2">{d.name}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
