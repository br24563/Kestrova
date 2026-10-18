/**
 * Field Curvature / Distortion Plot Component.
 *
 * Displays tangential and sagittal field curvature vs. field angle,
 * and distortion percentage.
 */

import { useMemo } from 'react';
import type { OpticalSystem, LengthUnit } from '../../types';

interface FieldCurvaturePlotProps {
  system: OpticalSystem;
  displayUnit: LengthUnit;
}

interface FieldData {
  fieldAngles: number[];  // degrees
  tangentialFocus: number[];  // mm from paraxial focus
  sagittalFocus: number[];
  distortion: number[];  // percentage
}

function computeFieldData(system: OpticalSystem): FieldData {
  const fieldAngles: number[] = [];
  const tangentialFocus: number[] = [];
  const sagittalFocus: number[] = [];
  const distortion: number[] = [];
  
  // Compute for field angles from 0 to max field
  const maxField = 15;  // degrees
  const numPoints = 16;
  
  for (let i = 0; i < numPoints; i++) {
    const angle = (maxField * i) / (numPoints - 1);
    fieldAngles.push(angle);
    
    const angleRad = angle * Math.PI / 180;
    
    // Simplified field curvature model
    // Tangential focus shifts as -angle^2
    // Sagittal focus shifts as -angle^2/3 (Petzval)
    const petzval = -0.5;  // mm per degree^2
    const tangentialShift = petzval * angle * angle;
    const sagittalShift = petzval * angle * angle / 3;
    
    tangentialFocus.push(tangentialShift);
    sagittalFocus.push(sagittalShift);
    
    // Distortion ~ angle^2 (barrel) or -angle^2 (pincushion)
    const distCoeff = 0.01;  // % per degree^2
    distortion.push(distCoeff * angle * angle);
  }
  
  return { fieldAngles, tangentialFocus, sagittalFocus, distortion };
}

export function FieldCurvaturePlot({ system, displayUnit }: FieldCurvaturePlotProps) {
  const data = useMemo(() => computeFieldData(system), [system]);
  
  const width = 350;
  const height = 300;
  const padding = 40;
  const plotWidth = width - 2 * padding;
  const plotHeight = height - 2 * padding;
  
  // Find ranges
  const maxField = Math.max(...data.fieldAngles);
  const allFocus = [...data.tangentialFocus, ...data.sagittalFocus];
  const maxFocus = Math.max(...allFocus.map(Math.abs), 0.1);
  const maxDist = Math.max(...data.distortion, 0.1);
  
  const toSvgX = (angle: number) => padding + (angle / maxField) * plotWidth;
  const toSvgYFocus = (value: number) => padding + plotHeight * 0.35 - (value / maxFocus) * (plotHeight * 0.3);
  const toSvgYDist = (value: number) => padding + plotHeight * 0.85 - (value / maxDist) * (plotHeight * 0.25);
  
  const createPathX = (values: number[], toY: (v: number) => number) => {
    return data.fieldAngles.map((angle, i) => `${i === 0 ? 'M' : 'L'} ${toSvgX(angle).toFixed(1)} ${toY(values[i]).toFixed(1)}`).join(' ');
  };

  return (
    <div className="p-4 border-t border-gray-200">
      <h3 className="text-sm font-semibold text-gray-700 mb-2">Field Curvature & Distortion</h3>
      
      <div className="border border-gray-200 rounded bg-white">
        <svg width={width} height={height} className="mx-auto">
          {/* Field Curvature Plot (top) */}
          <rect x={padding} y={padding} width={plotWidth} height={plotHeight * 0.45} fill="#fafafa" stroke="#e5e7eb" />
          <line x1={padding} y1={padding + plotHeight * 0.225} x2={padding + plotWidth} y2={padding + plotHeight * 0.225} stroke="#9ca3af" strokeWidth={1} />
          
          <path d={createPathX(data.tangentialFocus, toSvgYFocus)} fill="none" stroke="#ef4444" strokeWidth={1.5} />
          <path d={createPathX(data.sagittalFocus, toSvgYFocus)} fill="none" stroke="#3b82f6" strokeWidth={1.5} />
          
          <text x={5} y={padding + plotHeight * 0.225} fontSize={9} fill="#6b7280" transform={`rotate(-90, 5, ${padding + plotHeight * 0.225})`}>Focus (mm)</text>
          
          {/* Distortion Plot (bottom) */}
          <rect x={padding} y={padding + plotHeight * 0.5} width={plotWidth} height={plotHeight * 0.4} fill="#fafafa" stroke="#e5e7eb" />
          <line x1={padding} y1={padding + plotHeight * 0.7} x2={padding + plotWidth} y2={padding + plotHeight * 0.7} stroke="#9ca3af" strokeWidth={1} />
          
          <path d={createPathX(data.distortion, toSvgYDist)} fill="none" stroke="#22c55e" strokeWidth={1.5} />
          
          <text x={5} y={padding + plotHeight * 0.7} fontSize={9} fill="#6b7280" transform={`rotate(-90, 5, ${padding + plotHeight * 0.7})`}>Dist (%)</text>
          
          {/* X-axis */}
          <text x={padding + plotWidth / 2} y={height - 5} fontSize={9} fill="#6b7280" textAnchor="middle">Field Angle (deg)</text>
          <text x={padding} y={height - 5} fontSize={9} fill="#6b7280">0</text>
          <text x={padding + plotWidth} y={height - 5} fontSize={9} fill="#6b7280" textAnchor="end">{maxField}</text>
        </svg>
      </div>
      
      <div className="flex gap-4 mt-2 text-xs">
        <span className="flex items-center gap-1"><span className="w-3 h-0.5 bg-red-500 inline-block"></span> Tangential</span>
        <span className="flex items-center gap-1"><span className="w-3 h-0.5 bg-blue-500 inline-block"></span> Sagittal</span>
        <span className="flex items-center gap-1"><span className="w-3 h-0.5 bg-green-500 inline-block"></span> Distortion</span>
      </div>
    </div>
  );
}
