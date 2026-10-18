/**
 * Run a backend analysis whenever its inputs change, discarding results
 * from superseded requests.
 */

import { useEffect, useState } from "react";
import type { FieldExtent } from "../../api";
import type { LengthUnit } from "../../types";
import { fromMeters, LENGTH_UNIT_LABELS } from "../../types";

export function useAnalysis<T>(run: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    run()
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((err) => {
        if (!cancelled) {
          setData(null);
          setError(err instanceof Error ? err.message : "Analysis failed");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { data, error, loading };
}

/** Field fractions offered by the plots' field selector. */
export const FIELD_FRACTIONS = [0, 0.5, 0.7, 1];

/** "5.00°" or "10.00 mm": the actual field at a fraction of the full field. */
export function describeField(extent: FieldExtent, fraction: number, unit: LengthUnit): string {
  const v = extent.field_max * fraction;
  return extent.field_unit === "deg"
    ? `${v.toFixed(2)}°`
    : `${fromMeters(v, unit).toFixed(3)} ${LENGTH_UNIT_LABELS[unit]}`;
}
