/**
 * OPD/Wavefront Plot Component.
 *
 * Displays Optical Path Difference vs. pupil coordinate.
 * Shows wavefront error across the exit pupil.
 */

import { useMemo } from 'react';
import type { OpticalSystem, LengthUnit } from '../../types';

interface OPDPlotProps {
  system: OpticalSystem;
  fieldAngle?: number;
  wavelength?: number;
  displayUnit: LengthUnit;
}

interface OPDData {
  pupil: number[];
  opd: number[];  // waves
  wrapped: number[];  // wrapped to [-0.5, 0.5]
}

function computeOPD(system: OpticalSystem, fieldAngleDeg: number, wavelength: number): OPDData {
  const numPoints = 51;
  const pupil: number[] = [];
  const opd: number[] = [];
  const wrapped: number[] = [];
  
  const fieldAngle = fieldAngleDeg * Math.PI / 180;
  
  // Simplified OPD model
  // Defocus: py^2
  // Spherical: py^4
  // Coma: py^3 * sin(field)
  // Astigmatism: py^2 * cos(2*field)
  for (let i = 0; i < numPoints; i++) {
    const py = -1 + (2 * i) / (numPoints - 1);
    pupil.push(py);
    
    const defocus = 0.5 * py * py;
    const spherical = 0.25 * Math.pow(py, 4);
    const coma = 0.15 * Math.pow(py, 3) * Math.sin(fieldAngle);
    const astig = 0.1 * py * py * Math.cos(2 * fieldAngle);
    
    const opdValue = (defocus + spherical + coma + astig) / (wavelength * 1e6);  // convert to waves
    opd.push(opdValue);
    
    // Wrap to [-0.5, 0.5]
    let w = opdValue % 1;
    if (w > 0.5) w -= 1;
    if (w < -0.5) w += 1;
    wrapped.push(w);
  }
  
  return { pupil, opd, wrapped };
}

export function OPDPlot({ system, fieldAngle = 0, wavelength = 550e-9, displayUnit }: OPDPlotProps) {
  const data = useMemo(() => computeOPD(system, fieldAngle, wavelength), [system, fieldAngle, wavelength]);
  
  const width = 350;
  const height = 200;
  const padding = 40;
  const plotWidth = width - 2 * padding;
  const plotHeight = height - 2 * padding;
  
  const maxOpd = Math.max(...data.opd.map(Math.abs), 0.1);
  
  const toSvgX = (pupil: number) => padding + (pupil + 1) / 2 * plotWidth;
  const toSvgY = (opd: number) => padding + plotHeight / 2 - (opd / maxOpd) * (plotHeight / 2) * 0.9;
  
  const createPath = (values: number[]) => {
    return data.pupil.map((p, i) => `${i === 0 ? 'M' : 'L'} ${toSvgX(p).toFixed(1)} ${toSvgY(values[i]).toFixed(1)}`).join(' ');
  };
  
  // Compute RMS and PV
  const rms = Math.sqrt(data.opd.reduce((sum, v) => sum + v * v, 0) / data.opd.length);
  const pv = Math.max(...data.opd) - Math.min(...data.opd);

  return (
    <div className="p-4 border-t border-gray-200">
      <div className="flex justify-between items-center mb-2">
        <h3 className="text-sm font-semibold text-gray-700">OPD/Wavefront (Field: {fieldAngle}\u00B0)</h3>
        <div className="flex gap-3 text-xs text-gray-500">
          <span>RMS: {rms.toFixed(3)} \u03BB</span>
          <span>P-V: {pv.toFixed(3)} \u03BB</span>
        </div>
      </div>
      
      <div className="border border-gray-200 rounded bg-white">
        <svg width={width} height={height} className="mx-auto">
          <rect x={padding} y={padding} width={plotWidth} height={plotHeight} fill="#fafafa" stroke="#e5e7eb" />
          <line x1={padding} y1={padding + plotHeight / 2} x2={padding + plotWidth} y2={padding + plotHeight / 2} stroke="#9ca3af" strokeWidth={1} />
          
          {/* Diffraction limit reference */}
          <line x1={padding} y1={padding + plotHeight / 2 - 0.25 * (plotHeight / 2) * 0.9 / maxOpd} 
                x2={padding + plotWidth} y2={padding + plotHeight / 2 - 0.25 * (plotHeight / 2) * 0.9 / maxOpd} 
                stroke="#22c55e" strokeWidth={1} strokeDasharray="4,2" />
          <line x1={padding} y1={padding + plotHeight / 2 + 0.25 * (plotHeight / 2) * 0.9 / maxOpd} 
                x2={padding + plotWidth} y2={padding + plotHeight / 2 + 0.25 * (plotHeight / 2) * 0.9 / maxOpd} 
                stroke="#22c55e" strokeWidth={1} strokeDasharray="4,2" />
          
          <path d={createPath(data.opd)} fill="none" stroke="#3b82f6" strokeWidth={1.5} />
          
          <text x={padding} y={height - 5} fontSize={9} fill="#6b7280">-1.0</text>
          <text x={padding + plotWidth / 2} y={height - 5} fontSize={9} fill="#6b7280" textAnchor="middle">0</text>
          <text x={padding + plotWidth} y={height - 5} fontSize={9} fill="#6b7280" textAnchor="end">1.0</text>
          <text x={5} y={padding + plotHeight / 2} fontSize={9} fill="#6b7280" transform={`rotate(-90, 5, ${padding + plotHeight / 2})`}>OPD (\u03BB)</text>
        </svg>
      </div>
      
      <div className="flex gap-4 mt-2 text-xs">
        <span className="flex items-center gap-1"><span className="w-3 h-0.5 bg-blue-500 inline-block"></span> OPD</span>
        <span className="flex items-center gap-1"><span className="w-3 h-0.5 bg-green-500 inline-block" style={{borderTop: '1px dashed'}}></span> \u03BB/4 limit</span>
      </div>
    </div>
  );
}
