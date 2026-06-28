const LIGHTS = [
  {
    key: "showAutoAccept",
    routing: "auto_accept",
    color: "bg-soft-accept",
    glow: "shadow-softGlowGreen",
    ring: "ring-soft-accept/50",
    label: "Auto Accept",
    short: "Accept",
    countKey: "auto_accept",
  },
  {
    key: "showFlag",
    routing: "flag_for_review",
    color: "bg-soft-flag",
    glow: "shadow-softGlowYellow",
    ring: "ring-soft-flag/50",
    label: "Flag for Review",
    short: "Review",
    countKey: "flag_for_review",
  },
  {
    key: "showReject",
    routing: "reject",
    color: "bg-soft-reject",
    glow: "shadow-softGlowRed",
    ring: "ring-soft-reject/50",
    label: "Reject",
    short: "Reject",
    countKey: "reject",
  },
];

export { LIGHTS };

export default function TrafficLights({
  filters,
  onToggle,
  counts,
  selectedPatient,
  filteredCounts,
  focusMode = false,
  layout = "vertical",
  size = "md",
}) {
  const circleSize = size === "lg" ? "w-16 h-16" : "w-11 h-11";

  return (
    <div className={layout === "horizontal" ? "flex flex-col gap-3" : "flex flex-col gap-4"}>
      {!focusMode && (
        <p className="text-[10px] uppercase tracking-widest text-muted font-semibold">
          Routing
        </p>
      )}
      <div
        className={
          layout === "horizontal"
            ? "flex justify-center gap-10"
            : "flex flex-col gap-5"
        }
      >
        {LIGHTS.map((light) => {
          const selectedMatch =
            selectedPatient && selectedPatient.routing === light.routing;
          const isOn = focusMode
            ? selectedMatch
            : filters[light.key];
          const glow = isOn ? light.glow : "";
          const count = focusMode && selectedMatch
            ? 1
            : counts[light.countKey];

          return (
            <button
              key={light.key}
              type="button"
              onClick={() => !focusMode && onToggle?.(light.key)}
              disabled={focusMode}
              className={[
                "group flex items-center gap-3 text-left transition-all",
                focusMode && !selectedMatch ? "opacity-20 scale-90 pointer-events-none" : "",
                layout === "horizontal" ? "flex-col items-center text-center" : "",
              ].join(" ")}
              title={focusMode ? light.label : `${isOn ? "Hide" : "Show"} ${light.label}`}
            >
              <div
                className={[
                  "relative rounded-full border-2 transition-all duration-500",
                  circleSize,
                  light.color,
                  isOn ? "opacity-100 border-white/30" : "opacity-20 border-transparent",
                  glow,
                  selectedMatch ? `ring-4 ${light.ring} scale-110` : "",
                ].join(" ")}
              >
                <div
                  className={[
                    "absolute inset-1.5 rounded-full",
                    isOn ? "bg-white/30" : "bg-black/20",
                  ].join(" ")}
                />
              </div>
              <div>
                <div className={`font-medium text-white/90 ${size === "lg" ? "text-base" : "text-sm"}`}>
                  {size === "lg" ? light.label : light.short}
                </div>
                <div className={`text-muted mono ${size === "lg" ? "text-sm" : "text-xs"}`}>
                  {focusMode && selectedMatch ? (
                    <span className="text-2xl font-semibold text-white block mt-1">1</span>
                  ) : (
                    <>
                      <span className="text-lg font-semibold text-white/80">{count}</span>
                      <span className="text-muted"> · {filteredCounts[light.countKey]} shown</span>
                    </>
                  )}
                </div>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
