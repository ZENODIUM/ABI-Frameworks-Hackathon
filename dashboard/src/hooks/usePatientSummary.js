import { useEffect, useRef, useState } from "react";

const cache = new Map();

export function usePatientSummary(patient) {
  const [summary, setSummary] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const pid = patient?.patient_id;
  const abortRef = useRef(null);

  useEffect(() => {
    if (!pid) {
      setSummary("");
      setError(null);
      return;
    }

    if (cache.has(pid)) {
      setSummary(cache.get(pid));
      setError(null);
      setLoading(false);
      return;
    }

    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    setLoading(true);
    setError(null);
    setSummary("");

    fetch("/api/summarize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ patient }),
      signal: ctrl.signal,
    })
      .then(async (r) => {
        const data = await r.json();
        if (!r.ok) throw new Error(data.error || "Summary failed");
        return data.summary;
      })
      .then((text) => {
        cache.set(pid, text);
        setSummary(text);
        setLoading(false);
      })
      .catch((e) => {
        if (e.name === "AbortError") return;
        setError(e.message);
        setLoading(false);
      });

    return () => ctrl.abort();
  }, [pid, patient]);

  return { summary, loading, error };
}
