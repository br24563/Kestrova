/**
 * Optical Bench Visualization Component.
 *
 * Renders an SVG visualization of the optical system, including:
 * - The optical axis (horizontal line)
 * - The object (arrow)
 * - Lenses (vertical lines with focal length indicators)
 * - The image plane (vertical line)
 * - Rays propagating through the system
 *
 * The visualization supports zoom and pan via mouse controls.
 */

import { useRef, useState } from "react";
import type { OpticalSystem, RayTraceResult, AnalysisResult, ThinLens } from "../types";
import { toMM } from "../types";

interface OpticalBenchProps {
  system: OpticalSystem;
  rayResult: RayTraceResult | null;
  analysis: AnalysisResult | null;
}

const RAY_COLORS: Record<string, string> = {
  chief: "#ef4444",
  marginal: "#3b82f6",
  fill: "#22c55e",
};

const PIXELS_PER_METER = 800;
const MARGIN_LEFT = 60;
const OPTICAL_AXIS_Y = 200;
const COMPONENT_HEIGHT = 120;

export function OpticalBench({ system, rayResult, analysis }: OpticalBenchProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [scale, setScale] = useState(1);
  const [translateX, setTranslateX] = useState(0);
  const [translateY, setTranslateY] = useState(0);
  const [isDragging, setIsDragging] = useState(false);
  const [lastPos, setLastPos] = useState({ x: 0, y: 0 });

  const allPositions = [
    system.object.position,
    ...system.components.map((c) => c.position),
    system.image_plane.position,
  ];
  const minZ = Math.min(...allPositions) - 0.02;
  const maxZ = Math.max(...allPositions) + 0.02;
  const systemLength = maxZ - minZ;

  const containerWidth = 800;
  const autoScale = Math.min(PIXELS_PER_METER, containerWidth / systemLength);
  const effectiveScale = autoScale * scale;

  const toSvgX = (z: number) => MARGIN_LEFT + (z - minZ) * effectiveScale;
  const toSvgY = (y: number) => OPTICAL_AXIS_Y - y * effectiveScale;

  const handleMouseDown = (e: React.MouseEvent) => {
    setIsDragging(true);
    setLastPos({ x: e.clientX, y: e.clientY });
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!isDragging) return;
    const dx = e.clientX - lastPos.x;
    const dy = e.clientY - lastPos.y;
    setTranslateX(translateX + dx);
    setTranslateY(translateY + dy);
    setLastPos({ x: e.clientX, y: e.clientY });
  };

  const handleMouseUp = () => {
    setIsDragging(false);
  };

  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const delta = -e.deltaY * 0.001;
    setScale(Math.max(0.1, Math.min(5, scale + delta)));
  };

    const drawLens = (comp: ThinLens) => {
    const x = toSvgX(comp.position);
    const lensWidth = 20;
    const halfHeight = COMPONENT_HEIGHT / 2;

    return (
      <g key={comp.id} className="lens">
        <polygon
          points={`${x - lensWidth},${OPTICAL_AXIS_Y - halfHeight} ${x + lensWidth},${OPTICAL_AXIS_Y - halfHeight} ${x},${OPTICAL_AXIS_Y + halfHeight}`}
          fill="#3b82f6"
          fillOpacity={0.3}
          stroke="#3b82f6"
          strokeWidth={2}
        />
        <text x={x} y={OPTICAL_AXIS_Y - halfHeight - 10} textAnchor="middle" fontSize={12} fill="#374151">
          {comp.id}
        </text>
        <text x={x} y={OPTICAL_AXIS_Y + halfHeight + 20} textAnchor="middle" fontSize={10} fill="#6b7280">
          f={toMM(comp.focal_length).toFixed(0)}mm
        </text>
        <text x={x} y={OPTICAL_AXIS_Y + 35} textAnchor="middle" fontSize={10} fill="#9ca3af">
          {toMM(comp.position).toFixed(0)}mm
        </text>
      </g>
    );
  };

  const drawObject = () => {
    const x = toSvgX(system.object.position);
    const height = system.object.height;
    const halfHeight = COMPONENT_HEIGHT / 2;

    return (
      <g key="object" className="object">
        <line
          x1={x}
          y1={toSvgY(height)}
          x2={x}
          y2={toSvgY(-height)}
          stroke="#ef4444"
          strokeWidth={3}
        />
        <text x={x - 10} y={toSvgY(height) - 5} textAnchor="end" fontSize={12} fill="#ef4444">
          Object
        </text>
        <text x={x - 10} y={OPTICAL_AXIS_Y + 35} textAnchor="end" fontSize={10} fill="#9ca3af">
          {toMM(system.object.position).toFixed(0)}mm
        </text>
      </g>
    );
  };

  const drawImagePlane = () => {
    const x = toSvgX(system.image_plane.position);
    const halfHeight = COMPONENT_HEIGHT / 2;

    return (
      <g key="image_plane" className="image-plane">
        <line
          x1={x}
          y1={OPTICAL_AXIS_Y - halfHeight}
          x2={x}
          y2={OPTICAL_AXIS_Y + halfHeight}
          stroke="#8b5cf6"
          strokeWidth={2}
          strokeDasharray="5,3"
        />
        <text x={x + 5} y={OPTICAL_AXIS_Y - halfHeight - 5} textAnchor="start" fontSize={12} fill="#8b5cf6">
          Image Plane
        </text>
        <text x={x} y={OPTICAL_AXIS_Y + 35} textAnchor="middle" fontSize={10} fill="#9ca3af">
          {toMM(system.image_plane.position).toFixed(0)}mm
        </text>
      </g>
    );
  };

  const drawRays = () => {
    if (!rayResult) return null;

    return rayResult.ray_paths.map((path, i) => {
      const color = RAY_COLORS[path.ray_type] || "#22c55e";
      const points = path.points.map((p) => `${toSvgX(p[0])},${toSvgY(p[1])}`);

      return (
        <g key={`ray-${i}`} className="ray">
          <polyline
            points={points.join(" ")}
            fill="none"
            stroke={color}
            strokeWidth={1.5}
            strokeOpacity={0.8}
          />
          <text
            x={toSvgX(path.points[0][0])}
            y={toSvgY(path.points[0][1]) - 5}
            textAnchor="middle"
            fontSize={9}
            fill={color}
          >
            {path.ray_type}
          </text>
        </g>
      );
    });
  };

  const drawOpticalAxis = () => {
    const startX = toSvgX(minZ);
    const endX = toSvgX(maxZ);

    return (
      <g className="optical-axis">
        <line
          x1={startX}
          y1={OPTICAL_AXIS_Y}
          x2={endX}
          y2={OPTICAL_AXIS_Y}
          stroke="#9ca3af"
          strokeWidth={1}
          strokeDasharray="2,2"
        />
        <polygon
          points={`${endX},${OPTICAL_AXIS_Y - 5} ${endX + 10},${OPTICAL_AXIS_Y} ${endX},${OPTICAL_AXIS_Y + 5}`}
          fill="#9ca3af"
        />
        <text x={endX + 15} y={OPTICAL_AXIS_Y + 4} fontSize={11} fill="#9ca3af">
          z (light travels right)
        </text>
      </g>
    );
  };

  const drawImageIndicator = () => {
    if (!rayResult) return null;
    const x = toSvgX(rayResult.image_position);
    return (
      <g className="image-indicator">
        <line x1={x} y1={OPTICAL_AXIS_Y - 10} x2={x} y2={OPTICAL_AXIS_Y + 10} stroke="#10b981" strokeWidth={2} />
        <text x={x} y={OPTICAL_AXIS_Y - 15} textAnchor="middle" fontSize={10} fill="#10b981">
          Image forms here
        </text>
      </g>
    );
  };

  const viewBoxWidth = 1000;
  const viewBoxHeight = 400;

  return (
    <div
      className="w-full h-full optical-bench-bg"
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
      onWheel={handleWheel}
    >
      <svg
        ref={svgRef}
        width="100%"
        height="100%"
        viewBox={`0 0 ${viewBoxWidth} ${viewBoxHeight}`}
        style={{ cursor: isDragging ? "grabbing" : "grab" }}
      >
        <defs>
          <marker id="arrowhead-red" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#ef4444" />
          </marker>
        </defs>

        <g transform={`translate(${translateX}, ${translateY})`}>
          {drawOpticalAxis()}
          {drawObject()}
          {system.components
            .filter((c): c is ThinLens => c.type === "thin_lens")
            .map((comp) => drawLens(comp))}
          {drawImagePlane()}
          {drawImageIndicator()}
          {drawRays()}
        </g>
      </svg>
    </div>
  );
}
