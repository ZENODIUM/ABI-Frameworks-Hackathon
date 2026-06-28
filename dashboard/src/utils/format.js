export function formatWoundType(type) {
  if (!type) return "—";
  return type.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function routingBadgeClass(routing) {
  if (routing === "auto_accept") return "text-soft-accept bg-soft-accept/10 border-soft-accept/25";
  if (routing === "flag_for_review") return "text-soft-flag bg-soft-flag/10 border-soft-flag/25";
  return "text-soft-reject bg-soft-reject/10 border-soft-reject/25";
}

export function dimLabel(val) {
  if (val === null || val === undefined || val === "") return "—";
  return `${val} cm`;
}

export function dimsRow(p) {
  const l = p.length_cm ?? "—";
  const w = p.width_cm ?? "—";
  const d = p.depth_cm ?? "—";
  if (l === "—" && w === "—" && d === "—") return "—";
  return `${l} × ${w} × ${d}`;
}
