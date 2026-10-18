/**
 * Chromatic Aberration Plot Component.
 *
 * Displays Longitudinal Chromatic Aberration (LCA) and
 * Transverse Chromatic Aberration (TCA) vs. wavelength.
 */

import { useMemo } from 'react';
import type { OpticalSystem, LengthUnit } from '../../types';
import { fromMeters } from '../../types';

interface ChromaticAberrationPlotProps {
  system: OpticalSystem;
  displayUnit: LengthUnit;
}

interface ChromaticData {
  wavelengths: number[];  // nm
  imagePositions: number[];  // mm from reference
  imageHeights: number[];  // mm
}

function computeChromaticData(system: OpticalSystem): ChromaticData {
  const wavelengths: number[] = [];
  const imagePositions: number[] = [];
  const imageHeights: number[] = [];
  
  // Compute for wavelengths from 400nm to 700nm
  const numPoints = 31;
  const lambdaMin = 400e-9;
  const lambdaMax = 700e-9;
  
  // Reference at 550nm
  const lambdaRef = 550e-9;
  let refPosition = 0;
  let refHeight = 0;
  
  // First pass: compute reference
  for (let i = 0; i < numPoints; i++) {
    const lambda = lambdaMin + (lambdaMax - lambdaMin) * i / (numPoints - 1);
    wavelengths.push(lambda * 1e9);
    
    // Simplified chromatic model
    // Image position shifts with dispersion
    const n = 1.5 + 0.01 * (550 - lambda * 1e9) / 100;  // simplified dispersion
    const f = 0.1;  // 100mm base focal length
    const fLambda = f * (n - 1) / (1.5 - 1);  // scale by index
    
    const s = -0.2;  // object at 200mm
    const sPrime = fLambda * s / (s + fLambda);
    
    if (Math.abs(lambda - lambdaRef) < 1e-10) {
      refPosition = sPrime;
      refHeight = sPrime / s * 0.01;  // magnification * object height
    }
  }
  
  // Second pass: compute relative to reference
  for (let i = 0; i < numPoints; i++) {
    const lambda = lambdaMin + (lambdaMax - lambdaMin) * i / (numPoints - 1);
    const n = 1.5 + 0.01 * (550 - lambda * 1e9) / 100;
    const f = 0.1;
    const fLambda = f * (n - 1) / (1.5 - 1);
    const s = -0.2;
    const sPrime = fLambda * s / (s + fLambda);
    
    imagePositions.push((sPrime - refPosition) * 1000);  // mm
    imageHeights.push((sPrime / s * 0.01 - refHeight) * 1000);  // mm
  }
  
  return { wavelengths, imagePositions, imageHeights };
}

export function ChromaticAberrationPlot({ system, displayUnit }: ChromaticAberrationPlotProps) {
  const data = useMemo(() => computeChromaticData(system), [system]);
  
  const width = 350;
  const height = 250;
  const padding = 40;
  const plotWidth = width - 2 * padding;
  const plotHeight = height - 2 * padding;
  
  const maxPos = Math.max(...data.imagePositions.map(Math.abs), 0.01);
  const maxH = Math.max(...data.imageHeights.map(Math.abs), 0.01);
  
  const toSvgX = (wl: number) => padding + ((wl - 400) / 300) * plotWidth;
  const toSvgYPos = (value: number) => padding + plotHeight * 0.35 - (value / maxPos) * (plotHeight * 0.3);
  const toSvgYHeight = (value: number) => padding + plotHeight * 0.85 - (value / maxH) * (plotHeight * 0.25);
  
  const createPathX = (values: number[], toY: (v: number) => number) => {
    return data.wavelengths.map((wl, i) => `${i === 0 ? 'M' : 'L'} ${toSvgX(wl).toFixed(1)} ${toY(values[i]).toFixed(1)}`).join(' ');
  };
  
  // Compute LCA and TCA values
  const lca = Math.max(...data.imagePositions) - Math.min(...data.imagePositions);
  const tca = Math.max(...data.imageHeights) - Math.min(...data.imageHeights);

  return (
    <div className="p-4 border-t border-gray-200">
      <div className="flex justify-between items-center mb-2">
        <h3 className="text-sm font-semibold text-gray-700">Chromatic Aberration</h3>
        <div className="flex gap-3 text-xs text-gray-500">
          <span>LCA: {(lca * 1000).toFixed(2)} \u00B5m</span>
          <span>TCA: {(tca * 1000).toFixed(2)} \u00B5m</span>
        </div>
      </div>
      
      <div className="border border-gray-200 rounded bg-white">
        <svg width={width} height={height} className="mx-auto">
          {/* LCA Plot (top) */}
          <rect x={padding} y={padding} width={plotWidth} height={plotHeight * 0.45} fill="#fafafa" stroke="#e5e7eb" />
          <line x1={padding} y1={padding + plotHeight * 0.225} x2={padding + plotWidth} y2={padding + plotHeight * 0.225} stroke="#9ca3af" strokeWidth={1} />
          
          <path d={createPathX(data.imagePositions, toSvgYPos)} fill="none" stroke="#ef4444" strokeWidth={1.5} />
          
          <text x={5} y={padding + plotHeight * 0.225} fontSize={9} fill="#6b7280" transform={`rotate(-90, 5, ${padding + plotHeight * 0.225})`}>LCA (mm)</text>
          
          {/* TCA Plot (bottom) */}
          <rect x={padding} y={padding + plotHeight * 0.5} width={plotWidth} height={plotHeight * 0.4} fill="#fafafa" stroke="#e5e7eb" />
          <line x1={padding} y1={padding + plotHeight * 0.7} x2={padding + plotWidth} y2={padding + plotHeight * 0.7} stroke="#9ca3af" strokeWidth={1} />
          
          <path d={createPathX(data.imageHeights, toSvgYHeight)} fill="none" stroke="#3b82f6" strokeWidth={1.5} />
          
          <text x={5} y={padding + plotHeight * 0.7} fontSize={9} fill="#6b7280" transform={`rotate(-90, 5, ${padding + plotHeight * 0.7})`}>TCA (mm)</text>
          
          {/* X-axis */}
          <text x={padding + plotWidth / 2} y={height - 5} fontSize={9} fill="#6b7280" textAnchor="middle">Wavelength (nm)</text>
          <text x={padding} y={height - 5} fontSize={9} fill="#6b7280">400</text>
          <text x={padding + plotWidth / 2} y={height - 5} fontSize={9} fill="#6b7280" textAnchor="middle">550</text>
          <text x={padding + plotWidth} y={height - 5} fontSize={9} fill="#6b7280" textAnchor="end">700</text>
        </svg>
      </div>
      
      <div className="flex gap-4 mt-2 text-xs">
        <span className="flex items-center gap-1"><span className="w-3 h-0.5 bg-red-500 inline-block"></span> LCA (Longitudinal)</span>
        <span className="flex items-center gap-1"><span className="w-3 h-0.5 bg-blue-500 inline-block"></span> TCA (Transverse)</span>
      </div>
    </div>
  );
}
