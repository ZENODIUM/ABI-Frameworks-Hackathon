/** Pipeline funnel — spaced layout, soft connectors, small arrows */

const LINE = {
  main: "#94a3b8",
  branch: "#a5b4d4",
  reject: "#d4a88a",
  route: "#9dc7a8",
};

function Box({ x, y, w, label, count, color, sub, small }) {
  const h = small ? 58 : 74;
  return (
    <g>
      <rect
        x={x}
        y={y}
        width={w}
        height={h}
        rx={10}
        fill={color}
        fillOpacity={0.1}
        stroke={color}
        strokeOpacity={0.4}
        strokeWidth={1.25}
      />
      <text x={x + w / 2} y={y + 18} textAnchor="middle" fill="#94a3b8" fontSize={9} fontWeight={600}>
        {label.toUpperCase()}
      </text>
      <text
        x={x + w / 2}
        y={y + (small ? 40 : 46)}
        textAnchor="middle"
        fill="#f1f5f9"
        fontSize={small ? 22 : 28}
        fontWeight={600}
      >
        {count}
      </text>
      {sub && (
        <text x={x + w / 2} y={y + (small ? 54 : 62)} textAnchor="middle" fill="#94a3b8" fontSize={8}>
          {sub}
        </text>
      )}
    </g>
  );
}

/** Thin connector — arrow only on terminal vertical drops */
function Connector({ x1, y1, x2, y2, color = LINE.main, arrow = false }) {
  const isVert = Math.abs(x2 - x1) < 2;
  const len = Math.hypot(x2 - x1, y2 - y1);
  if (len < 2) return null;
  return (
    <line
      x1={x1}
      y1={y1}
      x2={x2}
      y2={y2}
      stroke={color}
      strokeWidth={1.25}
      strokeOpacity={0.5}
      strokeDasharray="5 7"
      markerEnd={arrow && isVert && y2 > y1 ? "url(#arrow-sm)" : undefined}
    />
  );
}

function FlowLabel({ x, y, text, color = "#64748b" }) {
  return (
    <text x={x} y={y} textAnchor="middle" fill={color} fontSize={8} fontStyle="italic" opacity={0.85}>
      {text}
    </text>
  );
}

export default function PipelineMindmap({ patients }) {
  const total = patients.length;
  const extracted = patients.filter((p) => p.extraction_source && p.extraction_source !== "none").length;
  const llm = patients.filter((p) => p.used_llm).length;
  const mcb = patients.filter((p) => p.has_medicare_b).length;
  const reject = patients.filter((p) => p.routing === "reject").length;
  const noMcb = patients.filter((p) => p.reject_category === "no_medicare_b").length;
  const accept = patients.filter((p) => p.routing === "auto_accept").length;
  const flag = patients.filter((p) => p.routing === "flag_for_review").length;
  const missDepth = patients.filter((p) =>
    (p.missing_fields || []).some((f) => f.includes("depth"))
  ).length;
  const ambiguity = patients.filter((p) => p.has_ambiguity).length;

  const C = {
    ingest: "#93c5fd",
    extract: "#c4b5fd",
    gemini: "#a5b4fc",
    reject: "#fca5a5",
    mcb: "#7dd3fc",
    accept: "#86efac",
    flag: "#fde68a",
  };

  const cx = 500;
  const bw = 128;
  const regexX = 210;
  const regexMid = regexX + bw / 2;
  const geminiX = 662;
  const geminiMid = geminiX + bw / 2;
  const rejectX = 100;
  const rejectMid = rejectX + bw / 2;
  const mcbX = cx - bw / 2;
  const acceptX = 220;
  const acceptMid = acceptX + bw / 2;
  const flagX = 672;
  const flagMid = flagX + bw / 2;

  // Y positions — extra vertical gaps between stages
  const Y = {
    ingest: 32,
    split1: 128,
    extract: 148,
    merge1: 248,
    elig: 268,
    reject: 278,
    routeSplit: 388,
    route: 408,
    flagSplit: 508,
    flagDetail: 528,
    footer: 598,
  };

  const ingestBot = Y.ingest + 74;
  const extractBot = Y.extract + 74;
  const eligBot = Y.elig + 74;
  const routeBot = Y.route + 74;

  return (
    <div className="rounded-2xl border border-border/60 bg-panel/40 p-6 overflow-x-auto">
      <h3 className="text-sm font-semibold text-white/80 mb-1">Pipeline mindmap</h3>
      <p className="text-xs text-muted mb-4">
        Ingest → extract → eligibility gate → routing → review reasons
      </p>
      <svg viewBox="0 0 1000 620" className="w-full min-w-[860px] h-auto" role="img" aria-label="Pipeline funnel">
        <defs>
          <marker id="arrow-sm" markerWidth="5" markerHeight="5" refX="4" refY="2.5" orient="auto">
            <path d="M0,0 L5,2.5 L0,5 Z" fill="#94a3b8" fillOpacity={0.55} />
          </marker>
        </defs>

        <g>
          {/* Ingest → split → extract (wide fork) */}
          <Connector x1={cx} y1={ingestBot} x2={cx} y2={Y.split1} color={LINE.main} arrow />
          <Connector x1={cx} y1={Y.split1} x2={regexMid} y2={Y.split1} color={LINE.branch} />
          <Connector x1={regexMid} y1={Y.split1} x2={regexMid} y2={Y.extract} color={LINE.branch} arrow />
          <Connector x1={cx} y1={Y.split1} x2={geminiMid} y2={Y.split1} color={LINE.branch} />
          <Connector x1={geminiMid} y1={Y.split1} x2={geminiMid} y2={Y.extract} color={LINE.branch} arrow />

          {/* Extract → merge → eligibility */}
          <Connector x1={regexMid} y1={extractBot} x2={regexMid} y2={Y.merge1} color={LINE.branch} />
          <Connector x1={regexMid} y1={Y.merge1} x2={cx} y2={Y.merge1} color={LINE.main} />
          <Connector x1={geminiMid} y1={extractBot} x2={geminiMid} y2={Y.merge1} color={LINE.branch} />
          <Connector x1={geminiMid} y1={Y.merge1} x2={cx} y2={Y.merge1} color={LINE.main} />
          <Connector x1={cx} y1={Y.merge1} x2={cx} y2={Y.elig} color={LINE.main} arrow />

          {/* Eligibility: reject branch (left) + MCB (center) */}
          <Connector x1={cx} y1={Y.elig + 20} x2={rejectMid} y2={Y.elig + 20} color={LINE.reject} />
          <Connector x1={rejectMid} y1={Y.elig + 20} x2={rejectMid} y2={Y.reject} color={LINE.reject} arrow />

          {/* MCB → routing fork */}
          <Connector x1={cx} y1={eligBot} x2={cx} y2={Y.routeSplit} color={LINE.main} arrow />
          <Connector x1={cx} y1={Y.routeSplit} x2={acceptMid} y2={Y.routeSplit} color={LINE.route} />
          <Connector x1={acceptMid} y1={Y.routeSplit} x2={acceptMid} y2={Y.route} color={LINE.route} arrow />
          <Connector x1={cx} y1={Y.routeSplit} x2={flagMid} y2={Y.routeSplit} color={LINE.branch} />
          <Connector x1={flagMid} y1={Y.routeSplit} x2={flagMid} y2={Y.route} color={LINE.branch} arrow />

          {/* Flag → detail */}
          <Connector x1={flagMid} y1={routeBot} x2={flagMid} y2={Y.flagSplit} color={LINE.branch} arrow />
          <Connector x1={flagMid} y1={Y.flagSplit} x2={550} y2={Y.flagSplit} color={LINE.branch} />
          <Connector x1={550} y1={Y.flagSplit} x2={550} y2={Y.flagDetail} color={LINE.branch} arrow />
          <Connector x1={flagMid} y1={Y.flagSplit} x2={810} y2={Y.flagSplit} color={LINE.branch} />
          <Connector x1={810} y1={Y.flagSplit} x2={810} y2={Y.flagDetail} color={LINE.branch} arrow />
        </g>

        <text x={28} y={56} fill="#64748b" fontSize={9} fontWeight={600}>① INGEST</text>
        <text x={28} y={182} fill="#64748b" fontSize={9} fontWeight={600}>② EXTRACT</text>
        <text x={28} y={302} fill="#64748b" fontSize={9} fontWeight={600}>③ ELIGIBILITY</text>
        <text x={28} y={442} fill="#64748b" fontSize={9} fontWeight={600}>④ ROUTING</text>

        <FlowLabel x={cx} y={Y.split1 - 6} text="all patients" />
        <FlowLabel x={248} y={Y.elig + 14} text="no Medicare B → reject" color={LINE.reject} />
        <FlowLabel x={cx} y={Y.routeSplit - 6} text="MCB only" />
        <FlowLabel x={flagMid} y={Y.flagSplit - 6} text="of 14 flagged" />

        <Box x={mcbX} y={Y.ingest} w={bw} label="Ingested" count={total} color={C.ingest} sub="PCC API" />
        <Box x={regexX} y={Y.extract} w={bw} label="Regex extract" count={extracted} color={C.extract} sub="assess + notes" />
        <Box x={geminiX} y={Y.extract} w={bw} label="Gemini gap-fill" count={llm} color={C.gemini} sub="MCB gaps only" />
        <Box x={rejectX} y={Y.reject} w={bw} label="Rejected" count={reject} color={C.reject} sub={`${noMcb} no Medicare B`} />
        <Box x={mcbX} y={Y.elig} w={bw} label="Medicare B" count={mcb} color={C.mcb} sub="eligible" />
        <Box x={acceptX} y={Y.route} w={bw} label="Auto accept" count={accept} color={C.accept} sub="ready to bill" />
        <Box x={flagX} y={Y.route} w={bw} label="Flag review" count={flag} color={C.flag} sub="manual review" />
        <Box x={495} y={Y.flagDetail} w={110} label="Missing depth" count={missDepth} color={C.flag} sub="Envive 2D" small />
        <Box x={755} y={Y.flagDetail} w={110} label="Anomaly" count={ambiguity} color={C.flag} sub="depth > length" small />

        <line x1={80} y1={568} x2={920} y2={568} stroke="#334155" strokeWidth={1} strokeOpacity={0.4} />
        <text x={cx} y={Y.footer} textAnchor="middle" fill="#94a3b8" fontSize={10} opacity={0.9}>
          {total} → {reject} reject + {mcb} MCB → {accept} accept + {flag} flag = {accept + flag} MCB patients
        </text>
      </svg>
    </div>
  );
}
