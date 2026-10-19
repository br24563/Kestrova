/**
 * Spot Diagram Component.
 *
 * Real-ray spot diagram: where each traced ray meets the image plane,
 * plotted in x and y relative to the spot centroid, with equal scales on
 * both axes.
 */

import type { AnalysisResult, LengthUnit } from "../types";
import { fromMeters, LENGTH_UNIT_LABELS } from "../types";

interface SpotDiagramProps {
  analysis: AnalysisResult | null;
  displayUnit: LengthUnit;
}

export function SpotDiagram({ analysis, displayUnit }: SpotDiagramProps) {
  const unitLabel = LENGTH_UNIT_LABELS[displayUnit];
  if (!analysis || analysis.spot_points.length === 0) {
    return (
      <div className="p-4 border-t border-gray-200">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-lg font-semibold text-gray-800">Spot Diagram</h2>
        </div>
        <p className="text-gray-500">No spot data available.</p>
      </div>
    );
  }

  const pts = analysis.spot_points;
  const extent = Math.max(
    ...pts.map(([x, y]) => Math.max(Math.abs(x), Math.abs(y))),
    1e-12,
  );

  const size = 240;
  const padding = 30;
  const plot = size - 2 * padding;
  const scale = plot / (2 * extent);
  const cx0 = padding + plot / 2;
  const cy0 = padding + plot / 2;
  const toSvg = ([x, y]: [number, number]) => [
    cx0 + x * scale,
    cy0 - y * scale,
  ];

  const exportSvg = () => {
    const svgElement = document.getElementById("spot-diagram-svg");
    if (!svgElement) return;
    const serializer = new XMLSerializer();
    const svgString = serializer.serializeToString(svgElement);
    const blob = new Blob([svgString], { type: "image/svg+xml" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "spot-diagram.svg";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="p-4 border-t border-gray-200">
      <div className="flex justify-between items-center mb-2">
        <h2 className="text-lg font-semibold text-gray-800">Spot Diagram</h2>
        <button
          onClick={exportSvg}
          className="px-2 py-1 text-xs bg-gray-100 hover:bg-gray-200 rounded border border-gray-300"
          title="Export as SVG"
        >
          Export
        </button>
      </div>
      <div className="mb-2">
        <span className="text-xs text-gray-500">
          RMS Spot Radius:{" "}
          {fromMeters(analysis.rms_spot_radius, displayUnit).toFixed(4)}{" "}
          {unitLabel}
        </span>
      </div>
      <div className="border border-gray-200 rounded bg-white overflow-auto">
        <svg
          id="spot-diagram-svg"
          width={size}
          height={size}
          className="mx-auto"
        >
          <rect
            x={padding}
            y={padding}
            width={plot}
            height={plot}
            fill="#f8fafc"
            stroke="#e2e8f0"
            strokeWidth={1}
          />
          <line
            x1={padding}
            y1={cy0}
            x2={padding + plot}
            y2={cy0}
            stroke="#94a3b8"
            strokeWidth={1}
            strokeDasharray="3,3"
          />
          <line
            x1={cx0}
            y1={padding}
            x2={cx0}
            y2={padding + plot}
            stroke="#94a3b8"
            strokeWidth={1}
            strokeDasharray="3,3"
          />
          {pts.map((point, i) => {
            const [cx, cy] = toSvg(point);
            return (
              <circle
                key={i}
                cx={cx}
                cy={cy}
                r={2}
                fill="#3b82f6"
                fillOpacity={0.7}
              />
            );
          })}
          <text
            x={size / 2}
            y={size - 8}
            textAnchor="middle"
            fontSize={10}
            fill="#94a3b8"
          >
            x, y relative to centroid; box half-width{" "}
            {fromMeters(extent, displayUnit).toPrecision(3)} {unitLabel}
          </text>
        </svg>
      </div>
      <div className="mt-2 text-xs text-gray-500">
        <div>Number of rays: {analysis.spot_points.length}</div>
        <div>
          Largest ray offset from centroid:{" "}
          {fromMeters(extent, displayUnit).toPrecision(4)} {unitLabel}
        </div>
      </div>
    </div>
  );
}
