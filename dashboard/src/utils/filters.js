/** Default filter state — each toggle ON means that criterion is applied. */
export const DEFAULT_FILTERS = {
  // Routing visibility (traffic lights)
  showAutoAccept: true,
  showFlag: true,
  showReject: true,

  // Hard gates
  medicareBOnly: false,
  hideNoMedicareB: false,
  hideResolvedDx: false,
  hideNoWoundEvidence: false,

  // Completeness flags
  missingDepthOnly: false,
  missingStageOnly: false,
  missingLocationOnly: false,
  missingAnyField: false,

  // Ambiguity / cross-source
  ambiguitiesOnly: false,
  depthExceedsLength: false,
  sourceMismatch: false,

  // Other
  llmAssistedOnly: false,
  woundDxOnly: false,
};

export function applyFilters(patients, filters, search, selectedPatientId) {
  let list = [...patients];

  // Search — real-time across key fields
  if (search.trim()) {
    const q = search.trim().toLowerCase();
    list = list.filter((p) =>
      [
        p.patient_id,
        p.name,
        p.facility,
        p.wound_type,
        p.location,
        p.routing,
        p.routing_label,
        p.reason,
        p.primary_payer,
        p.ambiguity_flags,
        ...(p.missing_fields || []),
      ]
        .filter(Boolean)
        .some((v) => String(v).toLowerCase().includes(q))
    );
  }

  // Routing toggles
  const routingAllowed = new Set();
  if (filters.showAutoAccept) routingAllowed.add("auto_accept");
  if (filters.showFlag) routingAllowed.add("flag_for_review");
  if (filters.showReject) routingAllowed.add("reject");
  if (routingAllowed.size > 0) {
    list = list.filter((p) => routingAllowed.has(p.routing));
  }

  if (filters.medicareBOnly) {
    list = list.filter((p) => p.has_medicare_b);
  }

  if (filters.hideNoMedicareB) {
    list = list.filter((p) => p.reject_category !== "no_medicare_b");
  }

  if (filters.hideResolvedDx) {
    list = list.filter((p) => p.reject_category !== "resolved_diagnosis");
  }

  if (filters.hideNoWoundEvidence) {
    list = list.filter((p) => p.reject_category !== "no_wound_evidence");
  }

  if (filters.missingDepthOnly) {
    list = list.filter((p) =>
      (p.missing_fields || []).some((f) => f.includes("depth"))
    );
  }

  if (filters.missingStageOnly) {
    list = list.filter((p) =>
      (p.missing_fields || []).some((f) => f.includes("stage"))
    );
  }

  if (filters.missingLocationOnly) {
    list = list.filter((p) =>
      (p.missing_fields || []).some((f) => f.includes("location"))
    );
  }

  if (filters.missingAnyField) {
    list = list.filter((p) => (p.missing_fields || []).length > 0);
  }

  if (filters.ambiguitiesOnly) {
    list = list.filter((p) => p.has_ambiguity);
  }

  if (filters.depthExceedsLength) {
    list = list.filter((p) =>
      (p.ambiguity_types || []).includes("depth_exceeds_length")
    );
  }

  if (filters.sourceMismatch) {
    list = list.filter((p) =>
      (p.ambiguity_types || []).includes("source_mismatch")
    );
  }

  if (filters.llmAssistedOnly) {
    list = list.filter((p) => p.used_llm);
  }

  if (filters.woundDxOnly) {
    list = list.filter((p) => p.has_wound_dx);
  }

  if (selectedPatientId) {
    // selected row stays in list but we use it for traffic light highlight
  }

  return list;
}

export function countByRouting(patients) {
  return {
    auto_accept: patients.filter((p) => p.routing === "auto_accept").length,
    flag_for_review: patients.filter((p) => p.routing === "flag_for_review").length,
    reject: patients.filter((p) => p.routing === "reject").length,
  };
}

export const FILTER_GROUPS = [
  {
    title: "Hard Gates",
    items: [
      { key: "medicareBOnly", label: "Medicare B only" },
      { key: "hideNoMedicareB", label: "Hide no-MCB rejects" },
      { key: "hideResolvedDx", label: "Hide resolved dx rejects" },
      { key: "hideNoWoundEvidence", label: "Hide no-evidence rejects" },
    ],
  },
  {
    title: "Completeness",
    items: [
      { key: "missingAnyField", label: "Missing any field" },
      { key: "missingDepthOnly", label: "Missing depth" },
      { key: "missingStageOnly", label: "Missing stage" },
      { key: "missingLocationOnly", label: "Missing location" },
    ],
  },
  {
    title: "Ambiguities",
    items: [
      { key: "ambiguitiesOnly", label: "Has ambiguity flags" },
      { key: "depthExceedsLength", label: "Depth > length" },
      { key: "sourceMismatch", label: "Note vs assessment mismatch" },
    ],
  },
  {
    title: "Other",
    items: [
      { key: "llmAssistedOnly", label: "Gemini-assisted only" },
      { key: "woundDxOnly", label: "Active wound dx only" },
    ],
  },
];
