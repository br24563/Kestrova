/**
 * Interactive 2D Layout Component.
 *
 * Professional interactive optical layout with drag-to-edit,
 * ray fans, and surface visualization.
 */

import { useState, useRef, useCallback, useMemo } from 'react';
import type { OpticalSystem, RayTraceResult, OpticalComponent, ThinLens, ThickLens, ApertureStop, Mirror, LengthUnit } from '../../types';
import { fromMeters, LENGTH_UNIT_LABELS } from '../../types';

interface InteractiveLayoutProps {
  system: OpticalSystem;
  rayResult: RayTraceResult | null;
  displayUnit: LengthUnit;
  onSystemChange?: (system: OpticalSystem) => void;
}

interface DragState {
  isDragging: boolean;
  componentIndex: number | null;
  startX: number;
  startPosition: number;
}

const RAY_COLORS = {
  chief: '#ef4444',
  marginal: '#3b82f6',
  fill: '#22c55e',
};

export function InteractiveLayout({ system, rayResult, displayUnit, onSystemChange }: InteractiveLayoutProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [viewBox, setViewBox] = useState({ x: 0, y: -150, width: 800, height: 300 });
  const [dragState, setDragState] = useState<DragState>({
    isDragging: false,
    componentIndex: null,
    startX: 0,
    startPosition: 0,
  });
  const [showRays, setShowRays] = useState(true);
  const [showChiefMarginal, setShowChiefMarginal] = useState(true);

  const unitLabel = LENGTH_UNIT_LABELS[displayUnit];
  
  const allPositions = useMemo(() => [
    system.object.position,
    ...system.components.map(c => c.position),
    system.image_plane.position,
  ], [system]);
  
  const minZ = Math.min(...allPositions) - 0.05;
  const maxZ = Math.max(...allPositions) + 0.05;
  const systemLength = maxZ - minZ;
  
  const scale = viewBox.width / systemLength;
  const toSvgX = (z: number) => (z - minZ) * scale + viewBox.x;
  const toSvgY = (y: number) => viewBox.height / 2 - y * scale;

  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    const zoomFactor = e.deltaY > 0 ? 1.1 : 0.9;
    setViewBox(prev => {
      const newWidth = prev.width * zoomFactor;
      const newHeight = prev.height * zoomFactor;
      return {
        ...prev,
        x: prev.x + (prev.width - newWidth) / 2,
        y: prev.y + (prev.height - newHeight) / 2,
        width: newWidth,
        height: newHeight,
      };
    });
  }, []);

  const handleMouseDown = useCallback((e: React.MouseEvent, componentIndex: number) => {
    if (!onSystemChange) return;
    const comp = system.components[componentIndex];
    setDragState({
      isDragging: true,
      componentIndex,
      startX: e.clientX,
      startPosition: comp.position,
    });
  }, [system, onSystemChange]);

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (!dragState.isDragging || dragState.componentIndex === null || !onSystemChange) return;
    const dx = e.clientX - dragState.startX;
    const dz = dx / scale;
    const newPosition = dragState.startPosition + dz;
    onSystemChange({
      ...system,
      components: system.components.map((c, i) => 
        i === dragState.componentIndex ? { ...c, position: newPosition } : c
      ),
    });
  }, [dragState, scale, system, onSystemChange]);

  const handleMouseUp = useCallback(() => {
    setDragState(prev => ({ ...prev, isDragging: false, componentIndex: null }));
  }, []);

  const drawSurface = (comp: OpticalComponent, index: number) => {
    const x = toSvgX(comp.position);
    const isStop = comp.type === 'aperture';
    const apertureRadius = comp.type === 'thin_lens' 
      ? comp.aperture_diameter / 2 
      : comp.type === 'thick_lens'
        ? comp.aperture_diameter / 2
        : comp.type === 'aperture'
          ? comp.diameter / 2
          : 0.025;
    
    const halfHeight = Math.max(apertureRadius * scale, 30);
    
    return (
      <g key={index}>
        {comp.type === 'thin_lens' || comp.type === 'thick_lens' ? (
          <g
            onMouseDown={(e) => handleMouseDown(e, index)}
            style={{ cursor: onSystemChange ? 'move' : 'default' }}
          >
            <rect
              x={x - 4}
              y={toSvgY(apertureRadius) - halfHeight}
              width={8}
              height={halfHeight * 2}
              fill={isStop ? '#fef3c7' : '#bfdbfe'}
              stroke={isStop ? '#f59e0b' : '#3b82f6'}
              strokeWidth={isStop ? 2 : 1}
              rx={2}
            />
            <text
              x={x}
              y={toSvgY(apertureRadius) + 15}
              textAnchor="middle"
              fontSize={9}
              fill="#374151"
            >
              {comp.id}
            </text>
            {comp.type === 'thin_lens' && (
              <text
                x={x}
                y={toSvgY(-apertureRadius) - 8}
                textAnchor="middle"
                fontSize={8}
                fill="#6b7280"
              >
                f={fromMeters(comp.focal_length, displayUnit).toFixed(1)}{unitLabel}
              </text>
            )}
          </g>
        ) : comp.type === 'aperture' ? (
          <g>
            <line x1={x} y1={toSvgY(0)} x2={x} y2={toSvgY(apertureRadius)} stroke="#f59e0b" strokeWidth={3} />
            <line x1={x} y1={toSvgY(0)} x2={x} y2={toSvgY(-apertureRadius)} stroke="#f59e0b" strokeWidth={3} />
            <text x={x} y={toSvgY(apertureRadius) + 15} textAnchor="middle" fontSize={9} fill="#374151">{comp.id}</text>
          </g>
        ) : (
          <g>
            <line x1={x} y1={toSvgY(-halfHeight)} x2={x} y2={toSvgY(halfHeight)} stroke="#6b7280" strokeWidth={4} />
            <text x={x} y={toSvgY(halfHeight) + 15} textAnchor="middle" fontSize={9} fill="#374151">{comp.id}</text>
          </g>
        )}
      </g>
    );
  };

  const drawRays = () => {
    if (!rayResult || !showRays) return null;
    return (
      <g>
        {rayResult.ray_paths.map((path, i) => {
          const points = path.points.map(p => `${toSvgX(p[0])},${toSvgY(p[1])}`).join(' ');
          const color = RAY_COLORS[path.ray_type as keyof typeof RAY_COLORS] || RAY_COLORS.fill;
          return (
            <polyline key={i} points={points} fill="none" stroke={color} strokeWidth={1} strokeOpacity={0.7} />
          );
        })}
      </g>
    );
  };

  const drawChiefMarginal = () => {
    if (!showChiefMarginal) return null;
    const objectHeight = system.object.height;
    const firstComp = system.components[0];
    const apertureRadius = firstComp?.type === 'thin_lens' 
      ? firstComp.aperture_diameter / 2 
      : 0.0125;
    
    return (
      <g>
        {/* Chief ray */}
        <line
          x1={toSvgX(system.object.position)}
          y1={toSvgY(objectHeight)}
          x2={toSvgX(system.image_plane.position)}
          y2={toSvgY(-objectHeight * 0.5)}
          stroke={RAY_COLORS.chief}
          strokeWidth={1.5}
          strokeDasharray="4,2"
        />
        {/* Upper marginal */}
        <line
          x1={toSvgX(system.object.position)}
          y1={toSvgY(0)}
          x2={toSvgX(firstComp?.position ?? 0)}
          y2={toSvgY(apertureRadius)}
          stroke={RAY_COLORS.marginal}
          strokeWidth={1}
        />
        {/* Lower marginal */}
        <line
          x1={toSvgX(system.object.position)}
          y1={toSvgY(0)}
          x2={toSvgX(firstComp?.position ?? 0)}
          y2={toSvgY(-apertureRadius)}
          stroke={RAY_COLORS.marginal}
          strokeWidth={1}
        />
      </g>
    );
  };

  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden bg-white">
      <div className="bg-gray-100 px-3 py-2 border-b border-gray-200">
        <div className="flex justify-between items-center">
          <h3 className="text-sm font-semibold text-gray-700">Interactive Layout</h3>
          <div className="flex gap-2">
            <label className="flex items-center gap-1 text-xs">
              <input type="checkbox" checked={showRays} onChange={(e) => setShowRays(e.target.checked)} className="w-3 h-3" />
              Traced Rays
            </label>
            <label className="flex items-center gap-1 text-xs">
              <input type="checkbox" checked={showChiefMarginal} onChange={(e) => setShowChiefMarginal(e.target.checked)} className="w-3 h-3" />
              Chief/Marginal
            </label>
          </div>
        </div>
      </div>
      
      <svg
        ref={svgRef}
        width="100%"
        height={300}
        viewBox={`${viewBox.x} ${viewBox.y} ${viewBox.width} ${viewBox.height}`}
        onWheel={handleWheel}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        style={{ cursor: dragState.isDragging ? 'grabbing' : 'grab' }}
      >
        <line x1={toSvgX(minZ)} y1={toSvgY(0)} x2={toSvgX(maxZ)} y2={toSvgY(0)} stroke="#9ca3af" strokeWidth={1} strokeDasharray="4,2" />
        
        <g>
          <polygon
            points={`${toSvgX(system.object.position)},${toSvgY(0)} ${toSvgX(system.object.position - 0.005)},${toSvgY(system.object.height)} ${toSvgX(system.object.position + 0.005)},${toSvgY(system.object.height)}`}
            fill="#ef4444"
          />
          <text x={toSvgX(system.object.position)} y={toSvgY(system.object.height) - 8} textAnchor="middle" fontSize={9} fill="#374151">Object</text>
        </g>
        
        {system.components.map((comp, i) => drawSurface(comp, i))}
        
        <g>
          <line x1={toSvgX(system.image_plane.position)} y1={toSvgY(-system.object.height)} x2={toSvgX(system.image_plane.position)} y2={toSvgY(system.object.height)} stroke="#10b981" strokeWidth={2} />
          <text x={toSvgX(system.image_plane.position)} y={toSvgY(system.object.height) + 12} textAnchor="middle" fontSize={9} fill="#374151">Image</text>
        </g>
        
        {drawChiefMarginal()}
        {drawRays()}
      </svg>
      
      <div className="bg-gray-50 px-3 py-1 border-t border-gray-200 text-xs text-gray-500">
        Scroll to zoom \u2022 Drag components to move
      </div>
    </div>
  );
}
