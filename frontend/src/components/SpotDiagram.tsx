/**
 * Spot Diagram Component.
 *
 * Displays the spot diagram for the optical system, showing where
 * each ray intersects the image plane. For a perfect paraxial system,
 * all rays should converge to a single point.
 */

import type { AnalysisResult } from "../types";
import { toMM } from "../types";

interface SpotDiagramProps {
  analysis: AnalysisResult | null;
}

export function SpotDiagram({ analysis }: SpotDiagramProps) {
  if (!analysis || analysis.spot_points.length === 0) {
    return (
      <div className="p-4 border-t border-gray-200">
        <h2 className="text-lg font-semibold text-gray-800 mb-4">Spot Diagram</h2>
        <p className="text-gray-500">No spot data available.</p>
      </div>
    );
  }

  const spotYs = analysis.spot_points.map((p) => p[0]);
  const minY = Math.min(...spotYs);
  const maxY = Math.max(...spotYs);
  const range = Math.max(maxY - minY, 1e-9);

  const width = 300;
  const height = 200;
  const padding = 30;
  const plotWidth = width - 2 * padding;
  const plotHeight = height - 2 * padding;
  const scale = plotWidth / range;
  const centerY = padding + plotHeight / 2;

  const toSvgY = (y: number) => {
    const offset = (minY + maxY) / 2;
    return centerY - (y - offset) * scale;
  };

  return (
    <div className="p-4 border-t border-gray-200">
      <h2 className="text-lg font-semibold text-gray-800 mb-4">Spot Diagram</h2>
      <div className="mb-2">
        <span className="text-xs text-gray-500">
          RMS Spot Radius: {toMM(analysis.rms_spot_radius).toFixed(4)} mm
        </span>
      </div>
      <div className="border border-gray-200 rounded bg-white overflow-auto">
        <svg width={width} height={height} className="mx-auto">
          <rect x={padding} y={padding} width={plotWidth} height={plotHeight} fill="#f8fafc" stroke="#e2e8f0" strokeWidth={1} />
          <line x1={padding} y1={centerY} x2={padding + plotWidth} y2={centerY} stroke="#94a3b8" strokeWidth={1} strokeDasharray="3,3" />
          {analysis.spot_points.map((point, i) => {
            const cy = toSvgY(point[0]);
            const cx = padding + plotWidth / 2;
            return (
              <circle key={i} cx={cx} cy={cy} r={4}
                fill={i === 0 ? "#ef4444" : i === 1 ? "#3b82f6" : "#22c55e"}
                fillOpacity={0.7} stroke="#ffffff" strokeWidth={1} />
            );
          })}
          <text x={width / 2} y={height - 5} textAnchor="middle" fontSize={10} fill="#94a3b8">
            Ray height at image plane (mm)
          </text>
        </svg>
      </div>
      <div className="mt-2 text-xs text-gray-500">
        <div>Number of rays: {analysis.spot_points.length}</div>
        <div>Spot range: {toMM(minY).toFixed(4)} mm to {toMM(maxY).toFixed(4)} mm</div>
      </div>
    </div>
  );
}
