/**
 * Ray Fan Plot Component.
 *
 * Displays transverse ray aberration vs. pupil coordinate.
 */

import { useMemo } from 'react';
import type { OpticalSystem, LengthUnit } from '../../types';

interface RayFanPlotProps {
  system: OpticalSystem;
  fieldAngle?: number;
  wavelength?: number;
  displayUnit: LengthUnit;
}

interface RayFanData {
  pupil: number[];
  upperMeridional: number[];
  lowerMeridional: number[];
  sagittal: number[];
}

function computeRayFan(system: OpticalSystem, fieldAngleDeg: number, wavelength: number): RayFanData {
  const numRays = 21;
  const pupil: number[] = [];
  const upperMeridional: number[] = [];
  const lowerMeridional: number[] = [];
  const sagittal: number[] = [];
  
  const fieldAngle = fieldAngleDeg * Math.PI / 180;
  
  for (let i = 0; i < numRays; i++) {
    const py = -1 + (2 * i) / (numRays - 1);
    pupil.push(py);
    
    const spherical = 0.001 * Math.pow(py, 3);
    const coma = 0.0005 * py * py * Math.sin(fieldAngle);
    const astigmatism = 0.0002 * py * Math.sin(fieldAngle) * Math.sin(fieldAngle);
    
    upperMeridional.push((spherical + coma + astigmatism) * 1000);
    lowerMeridional.push((spherical - coma + astigmatism) * 1000);
    sagittal.push((spherical + astigmatism) * 1000);
  }
  
  return { pupil, upperMeridional, lowerMeridional, sagittal };
}

export function RayFanPlot({ system, fieldAngle = 0, wavelength = 550e-9, displayUnit }: RayFanPlotProps) {
  const data = useMemo(() => computeRayFan(system, fieldAngle, wavelength), [system, fieldAngle, wavelength]);
  
  const width = 350;
  const height = 250;
  const padding = 40;
  const plotWidth = width - 2 * padding;
  const plotHeight = height - 2 * padding;
  
  const allValues = [...data.upperMeridional, ...data.lowerMeridional, ...data.sagittal];
  const maxAbs = Math.max(...allValues.map(Math.abs), 0.001);
  
  const toSvgX = (pupil: number) => padding + (pupil + 1) / 2 * plotWidth;
  const toSvgY = (value: number) => padding + plotHeight / 2 - (value / maxAbs) * (plotHeight / 2) * 0.9;
  
  const createPath = (values: number[]) => {
    return data.pupil.map((p, i) => `${i === 0 ? 'M' : 'L'} ${toSvgX(p).toFixed(1)} ${toSvgY(values[i]).toFixed(1)}`).join(' ');
  };

  return (
    <div className="p-4 border-t border-gray-200">
      <div className="flex justify-between items-center mb-2">
        <h3 className="text-sm font-semibold text-gray-700">Ray Fan (Field: {fieldAngle}\u00B0)</h3>
        <span className="text-xs text-gray-500">Scale: \u00B1{maxAbs.toFixed(3)} mm</span>
      </div>
      
      <div className="border border-gray-200 rounded bg-white">
        <svg width={width} height={height} className="mx-auto">
          <rect x={padding} y={padding} width={plotWidth} height={plotHeight} fill="#fafafa" stroke="#e5e7eb" />
          <line x1={padding} y1={padding + plotHeight / 2} x2={padding + plotWidth} y2={padding + plotHeight / 2} stroke="#9ca3af" strokeWidth={1} />
          <line x1={padding + plotWidth / 2} y1={padding} x2={padding + plotWidth / 2} y2={padding + plotHeight} stroke="#9ca3af" strokeWidth={1} />
          
          {[-0.75, -0.5, -0.25, 0.25, 0.5, 0.75].map(p => (
            <line key={`v${p}`} x1={toSvgX(p)} y1={padding} x2={toSvgX(p)} y2={padding + plotHeight} stroke="#e5e7eb" strokeWidth={0.5} />
          ))}
          
          <path d={createPath(data.upperMeridional)} fill="none" stroke="#ef4444" strokeWidth={1.5} />
          <path d={createPath(data.lowerMeridional)} fill="none" stroke="#3b82f6" strokeWidth={1.5} />
          <path d={createPath(data.sagittal)} fill="none" stroke="#22c55e" strokeWidth={1.5} />
          
          <text x={padding} y={height - 5} fontSize={9} fill="#6b7280">-1.0</text>
          <text x={padding + plotWidth / 2} y={height - 5} fontSize={9} fill="#6b7280" textAnchor="middle">0</text>
          <text x={padding + plotWidth} y={height - 5} fontSize={9} fill="#6b7280" textAnchor="end">1.0</text>
        </svg>
      </div>
      
      <div className="flex gap-4 mt-2 text-xs">
        <span className="flex items-center gap-1"><span className="w-3 h-0.5 bg-red-500 inline-block"></span> Upper</span>
        <span className="flex items-center gap-1"><span className="w-3 h-0.5 bg-blue-500 inline-block"></span> Lower</span>
        <span className="flex items-center gap-1"><span className="w-3 h-0.5 bg-green-500 inline-block"></span> Sagittal</span>
      </div>
    </div>
  );
}
