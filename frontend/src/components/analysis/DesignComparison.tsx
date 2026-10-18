/**
 * Design Comparison Component.
 *
 * Side-by-side comparison of two optical designs.
 * Shows prescription differences, performance metrics, and visual diff.
 */

import type { OpticalSystem, AnalysisResult, LengthUnit } from '../../types';
import { fmtLen, fmtNum, LENGTH_UNIT_LABELS } from '../../types';

interface DesignComparisonProps {
  systemA: OpticalSystem;
  systemB: OpticalSystem;
  analysisA: AnalysisResult | null;
  analysisB: AnalysisResult | null;
  labelA?: string;
  labelB?: string;
  displayUnit: LengthUnit;
}

interface MetricComparison {
  metric: string;
  valueA: number | string;
  valueB: number | string;
  unit: string;
  advantage: 'a' | 'b' | 'tie';
  percentDiff: number | null;
}

export function DesignComparison({
  systemA,
  systemB,
  analysisA,
  analysisB,
  labelA = 'Design A',
  labelB = 'Design B',
  displayUnit,
}: DesignComparisonProps) {
  const unitLabel = LENGTH_UNIT_LABELS[displayUnit];
  
  const metrics: MetricComparison[] = [];
  
  if (analysisA && analysisB) {
    // null = infinite (e.g. the EFL of an afocal design)
    const comparisons: [string, number | null, number | null, string, boolean][] = [
      ['Effective Focal Length', analysisA.effective_focal_length, analysisB.effective_focal_length, unitLabel, false],
      ['Magnification', analysisA.magnification, analysisB.magnification, 'x', false],
      ['F-number', analysisA.f_number, analysisB.f_number, '', false],
      ['Numerical Aperture', analysisA.numerical_aperture, analysisB.numerical_aperture, '', false],
      ['RMS Spot Radius', analysisA.rms_spot_radius, analysisB.rms_spot_radius, unitLabel, true],
      ['Image Distance', analysisA.image_distance, analysisB.image_distance, unitLabel, false],
      ['Working Distance', analysisA.working_distance, analysisB.working_distance, unitLabel, false],
    ];
    
    for (const [metric, valA, valB, unit, lowerIsBetter] of comparisons) {
      const displayA = unit === unitLabel ? fmtLen(valA, displayUnit, 4) : fmtNum(valA, 4);
      const displayB = unit === unitLabel ? fmtLen(valB, displayUnit, 4) : fmtNum(valB, 4);
      
      let advantage: 'a' | 'b' | 'tie' = 'tie';
      let percentDiff: number | null = null;
      
      if (valA !== null && valB !== null && valA !== 0) {
        percentDiff = ((valB - valA) / Math.abs(valA)) * 100;
        // Only metrics with a clear direction get a winner; for focal
        // length, magnification, distances etc. "better" depends on the spec.
        if (lowerIsBetter) {
          advantage = valA < valB ? 'a' : valA > valB ? 'b' : 'tie';
        }
      }
      
      metrics.push({
        metric,
        valueA: displayA,
        valueB: displayB,
        unit,
        advantage,
        percentDiff,
      });
    }
  }
  
  // Count component differences
  const compDiffs: { surface: string; param: string; valA: string; valB: string }[] = [];
  const maxComps = Math.max(systemA.components.length, systemB.components.length);
  for (let i = 0; i < maxComps; i++) {
    const compA = systemA.components[i];
    const compB = systemB.components[i];
    
    if (!compA || !compB) {
      compDiffs.push({
        surface: `S${i + 1}`,
        param: 'Exists',
        valA: compA ? compA.type : '-',
        valB: compB ? compB.type : '-',
      });
      continue;
    }
    
    if (compA.type !== compB.type) {
      compDiffs.push({ surface: `S${i + 1}`, param: 'Type', valA: compA.type, valB: compB.type });
    }
    if (Math.abs(compA.position - compB.position) > 1e-6) {
      compDiffs.push({ surface: `S${i + 1}`, param: 'Position', valA: (compA.position * 1000).toFixed(3), valB: (compB.position * 1000).toFixed(3) });
    }
    if (compA.type === 'thin_lens' && compB.type === 'thin_lens') {
      if (Math.abs(compA.focal_length - compB.focal_length) > 1e-6) {
        compDiffs.push({ surface: `S${i + 1}`, param: 'Focal Length', valA: (compA.focal_length * 1000).toFixed(3), valB: (compB.focal_length * 1000).toFixed(3) });
      }
    }
  }

  return (
    <div className="p-4 border-t border-gray-200">
      <h3 className="text-sm font-semibold text-gray-700 mb-3">Design Comparison</h3>
      
      {/* Performance Metrics Table */}
      {metrics.length > 0 && (
        <div className="mb-4">
          <div className="text-xs text-gray-600 mb-1 font-medium">Performance Metrics</div>
          <table className="w-full text-xs border border-gray-200 rounded">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-2 py-1 text-left text-gray-600">Metric</th>
                <th className="px-2 py-1 text-right text-gray-600">{labelA}</th>
                <th className="px-2 py-1 text-right text-gray-600">{labelB}</th>
                <th className="px-2 py-1 text-right text-gray-600">Diff %</th>
              </tr>
            </thead>
            <tbody>
              {metrics.map((m, i) => (
                <tr key={i} className="border-t border-gray-100">
                  <td className="px-2 py-1 text-gray-700">{m.metric}</td>
                  <td className={`px-2 py-1 text-right font-mono ${m.advantage === 'a' ? 'text-green-600 font-medium' : ''}`}>
                    {m.valueA} {m.unit}
                  </td>
                  <td className={`px-2 py-1 text-right font-mono ${m.advantage === 'b' ? 'text-green-600 font-medium' : ''}`}>
                    {m.valueB} {m.unit}
                  </td>
                  <td className="px-2 py-1 text-right text-gray-500">
                    {m.percentDiff !== null ? `${m.percentDiff > 0 ? '+' : ''}${m.percentDiff.toFixed(2)}%` : '-'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      
      {/* Prescription Differences */}
      {compDiffs.length > 0 && (
        <div>
          <div className="text-xs text-gray-600 mb-1 font-medium">Prescription Differences</div>
          <table className="w-full text-xs border border-gray-200 rounded">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-2 py-1 text-left text-gray-600">Surface</th>
                <th className="px-2 py-1 text-left text-gray-600">Parameter</th>
                <th className="px-2 py-1 text-right text-gray-600">{labelA}</th>
                <th className="px-2 py-1 text-right text-gray-600">{labelB}</th>
              </tr>
            </thead>
            <tbody>
              {compDiffs.map((diff, i) => (
                <tr key={i} className="border-t border-gray-100">
                  <td className="px-2 py-1 text-gray-700">{diff.surface}</td>
                  <td className="px-2 py-1 text-gray-600">{diff.param}</td>n                  <td className="px-2 py-1 text-right font-mono">{diff.valA}</td>
                  <td className="px-2 py-1 text-right font-mono">{diff.valB}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      
      {compDiffs.length === 0 && metrics.length > 0 && (
        <div className="text-xs text-gray-500 italic">No prescription differences found.</div>
      )}
    </div>
  );
}
