/**
 * Prescription Editor Component.
 *
 * Spreadsheet-style surface editor for optical prescriptions.
 * Features:
 * - Inline editing of all surface parameters
 * - Solves (marginal ray angle, edge thickness, pickup)
 * - Variable locks for optimization
 * - Add/insert/delete surfaces
 * - Stop surface designation
 */

import { useState, useCallback } from 'react';
import type { SurfaceRow, SurfaceType } from './PrescriptionTypes';
import { DEFAULT_SURFACE, GLASS_CATALOG } from './PrescriptionTypes';
import type { OpticalSystem, OpticalComponent } from '../../types';

interface PrescriptionEditorProps {
  system: OpticalSystem;
  onSystemChange: (system: OpticalSystem) => void;
}

let nextSurfaceId = 100;

function createSurface(overrides: Partial<SurfaceRow> = {}): SurfaceRow {
  return {
    ...DEFAULT_SURFACE,
    ...overrides,
    id: nextSurfaceId++,
  };
}

function systemToSurfaces(system: OpticalSystem): SurfaceRow[] {
  const surfaces: SurfaceRow[] = [];
  
  // Object surface
  surfaces.push(createSurface({
    label: 'OBJ',
    type: 'image',
    radius: null,
    thickness: Math.abs(system.object.position - (system.components[0]?.position ?? 0)) * 1000,
    material: null,
    semiDiameter: system.object.height * 1000,
    isStop: false,
    isVariable: false,
  }));
  
  // Component surfaces
  let prevPosition = system.object.position;
  system.components.forEach((comp, index) => {
    const thickness = (comp.position - prevPosition) * 1000;
    
    if (comp.type === 'thin_lens') {
      const focalMm = comp.focal_length * 1000;
      const apertureMm = comp.aperture_diameter * 1000;
      surfaces.push(createSurface({
        label: comp.id,
        type: 'standard',
        radius: focalMm > 0 ? focalMm / 2 : focalMm / 2, // Simplified
        thickness: thickness,
        material: comp.material,
        semiDiameter: apertureMm / 2,
        apertureRadius: apertureMm / 2,
        isStop: index === 0,
        isVariable: true,
      }));
    } else if (comp.type === 'thick_lens') {
      const apertureMm = comp.aperture_diameter * 1000;
      surfaces.push(createSurface({
        label: comp.id,
        type: 'standard',
        radius: comp.radius1 * 1000,
        thickness: comp.thickness * 1000,
        material: comp.material,
        semiDiameter: apertureMm / 2,
        apertureRadius: apertureMm / 2,
        conic: 0,
        isStop: index === 0,
        isVariable: true,
      }));
    } else if (comp.type === 'aperture') {
      surfaces.push(createSurface({
        label: comp.id,
        type: 'aperture',
        radius: null,
        thickness: thickness,
        material: null,
        semiDiameter: comp.diameter * 1000 / 2,
        apertureRadius: comp.diameter * 1000 / 2,
        isStop: true,
        isVariable: false,
      }));
    }
    
    prevPosition = comp.position;
  });
  
  // Image surface
  const lastComp = system.components[system.components.length - 1];
  const lastThickness = lastComp 
    ? (system.image_plane.position - lastComp.position) * 1000
    : 0;
  surfaces.push(createSurface({
    label: 'IMG',
    type: 'image',
    radius: null,
    thickness: lastThickness,
    material: null,
    semiDiameter: system.object.height * 1000 * Math.abs(
      (system.image_plane.position - system.object.position) / 
      (system.object.position - (system.components[0]?.position ?? 0) || 1)
    ),
    isStop: false,
    isVariable: false,
  }));
  
  return surfaces;
}

function surfacesToSystem(surfaces: SurfaceRow[], baseSystem: OpticalSystem): OpticalSystem {
  const components: OpticalComponent[] = [];
  let currentPosition = surfaces[0] ? -(surfaces[0].thickness ?? 0) / 1000 : 0;
  
  for (let i = 1; i < surfaces.length - 1; i++) {
    const surf = surfaces[i];
    currentPosition += (surfaces[i - 1]?.thickness ?? 0) / 1000;
    
    if (surf.type === 'aperture') {
      components.push({
        type: 'aperture',
        id: surf.label || `APT${i}`,
        position: currentPosition,
        diameter: (surf.apertureRadius ?? surf.semiDiameter ?? 12.5) * 2 / 1000,
      });
    } else {
      // Standard surface - approximate as thick lens
      const radius = surf.radius ?? 100;
      const thickness = i < surfaces.length - 2 ? 0.005 : 0;
      components.push({
        type: 'thick_lens',
        id: surf.label || `L${i}`,
        position: currentPosition,
        radius1: radius / 1000,
        radius2: -radius / 1000,
        thickness: thickness,
        aperture_diameter: (surf.apertureRadius ?? surf.semiDiameter ?? 12.5) * 2 / 1000,
        material: surf.material ?? 'N-BK7',
      });
    }
  }
  
  // Calculate image position
  const imageThickness = surfaces[surfaces.length - 1]?.thickness ?? 0;
  const imagePosition = currentPosition + imageThickness / 1000;
  
  return {
    ...baseSystem,
    components,
    image_plane: { position: imagePosition },
  };
}

export function PrescriptionEditor({ system, onSystemChange }: PrescriptionEditorProps) {
  const [surfaces, setSurfaces] = useState<SurfaceRow[]>(() => systemToSurfaces(system));
  const [selectedCell, setSelectedCell] = useState<{ row: number; col: string } | null>(null);
  const [editValue, setEditValue] = useState<string>('');

  const updateSurface = useCallback((index: number, updates: Partial<SurfaceRow>) => {
    setSurfaces(prev => {
      const newSurfaces = [...prev];
      newSurfaces[index] = { ...newSurfaces[index], ...updates };
      
      // Update the actual system
      const newSystem = surfacesToSystem(newSurfaces, system);
      onSystemChange(newSystem);
      
      return newSurfaces;
    });
  }, [system, onSystemChange]);

  const addSurface = useCallback((afterIndex: number) => {
    setSurfaces(prev => {
      const newSurfaces = [...prev];
      const newSurface = createSurface({
        label: `S${newSurfaces.length - 1}`,
        type: 'standard',
        radius: 100,
        thickness: 5,
        material: 'N-BK7',
        isStop: false,
        isVariable: true,
      });
      newSurfaces.splice(afterIndex + 1, 0, newSurface);
      return newSurfaces;
    });
  }, []);

  const deleteSurface = useCallback((index: number) => {
    if (index === 0 || index === surfaces.length - 1) return; // Can't delete OBJ or IMG
    setSurfaces(prev => {
      const newSurfaces = prev.filter((_, i) => i !== index);
      const newSystem = surfacesToSystem(newSurfaces, system);
      onSystemChange(newSystem);
      return newSurfaces;
    });
  }, [surfaces.length, system, onSystemChange]);

  const toggleVariable = useCallback((index: number) => {
    updateSurface(index, { isVariable: !surfaces[index].isVariable });
  }, [surfaces, updateSurface]);

  const toggleStop = useCallback((index: number) => {
    // Only one stop allowed - clear others
    setSurfaces(prev => {
      const newSurfaces = prev.map((s, i) => ({
        ...s,
        isStop: i === index ? !s.isStop : false,
      }));
      const newSystem = surfacesToSystem(newSurfaces, system);
      onSystemChange(newSystem);
      return newSurfaces;
    });
  }, [system, onSystemChange]);

  const handleCellClick = (row: number, col: string, value: unknown) => {
    setSelectedCell({ row, col });
    setEditValue(value?.toString() ?? '');
  };

  const handleCellChange = () => {
    if (!selectedCell) return;
    const { row, col } = selectedCell;
    const surface = surfaces[row];
    
    let updates: Partial<SurfaceRow> = {};
    
    switch (col) {
      case 'radius':
        updates.radius = editValue === 'inf' || editValue === '' ? null : parseFloat(editValue);
        break;
      case 'thickness':
        updates.thickness = parseFloat(editValue) || 0;
        break;
      case 'material':
        updates.material = editValue || 'Air';
        break;
      case 'conic':
        updates.conic = parseFloat(editValue) || 0;
        break;
      case 'semiDiameter':
        updates.semiDiameter = parseFloat(editValue) || 12.5;
        break;
    }
    
    updateSurface(row, updates);
    setSelectedCell(null);
  };

  const renderCell = (surface: SurfaceRow, col: string) => {
    const isSelected = selectedCell?.row === surfaces.indexOf(surface) && selectedCell?.col === col;
    const value = surface[col as keyof SurfaceRow];
    
    if (isSelected) {
      return (
        <input
          type="text"
          value={editValue}
          onChange={(e) => setEditValue(e.target.value)}
          onBlur={handleCellChange}
          onKeyDown={(e) => {
            if (e.key === 'Enter') handleCellChange();
            if (e.key === 'Escape') setSelectedCell(null);
          }}
          className="w-full px-1 py-0.5 text-xs border border-blue-500 outline-none"
          autoFocus
        />
      );
    }
    
    if (value === null) {
      return <span className="text-gray-400 text-xs">Inf</span>;
    }
    
    return (
      <span className="text-xs text-gray-800">
        {typeof value === 'number' ? value.toFixed(4) : value}
      </span>
    );
  };

  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden bg-white">
      <div className="bg-gray-100 px-3 py-2 border-b border-gray-200 flex justify-between items-center">
        <h3 className="text-sm font-semibold text-gray-700">Surface Prescription</h3>
        <div className="flex gap-1">
          <button
            onClick={() => addSurface(surfaces.length - 2)}
            className="px-2 py-0.5 text-xs bg-blue-500 text-white rounded hover:bg-blue-600"
            title="Add surface before image"
          >
            + Add
          </button>
        </div>
      </div>
      
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              <th className="px-2 py-1 text-left text-gray-600 font-medium">#</th>
              <th className="px-2 py-1 text-left text-gray-600 font-medium">Type</th>
              <th className="px-2 py-1 text-left text-gray-600 font-medium">Label</th>
              <th className="px-2 py-1 text-center text-gray-600 font-medium">V</th>
              <th className="px-2 py-1 text-center text-gray-600 font-medium">Stop</th>
              <th className="px-2 py-1 text-right text-gray-600 font-medium">R (mm)</th>
              <th className="px-2 py-1 text-right text-gray-600 font-medium">T (mm)</th>
              <th className="px-2 py-1 text-left text-gray-600 font-medium">Material</th>
              <th className="px-2 py-1 text-right text-gray-600 font-medium">Conic</th>
              <th className="px-2 py-1 text-right text-gray-600 font-medium">Semi-Dia</th>
              <th className="px-2 py-1 text-center text-gray-600 font-medium">Del</th>
            </tr>
          </thead>
          <tbody>
            {surfaces.map((surface, index) => (
              <tr
                key={surface.id}
                className={`border-b border-gray-100 hover:bg-blue-50 ${
                  surface.isStop ? 'bg-yellow-50' : ''
                }`}
              >
                <td className="px-2 py-1 text-gray-500">{index}</td>
                <td className="px-2 py-1 text-gray-600">{surface.type.slice(0, 4).toUpperCase()}</td>
                <td className="px-2 py-1 font-medium text-gray-700">{surface.label}</td>
                <td className="px-2 py-1 text-center">
                  <input
                    type="checkbox"
                    checked={surface.isVariable}
                    onChange={() => toggleVariable(index)}
                    className="w-3 h-3"
                    disabled={index === 0 || index === surfaces.length - 1}
                  />
                </td>
                <td className="px-2 py-1 text-center">
                  <input
                    type="checkbox"
                    checked={surface.isStop}
                    onChange={() => toggleStop(index)}
                    className="w-3 h-3"
                    disabled={index === 0 || index === surfaces.length - 1}
                  />
                </td>
                <td
                  className="px-2 py-1 text-right cursor-pointer hover:bg-blue-100"
                  onClick={() => handleCellClick(index, 'radius', surface.radius)}
                >
                  {renderCell(surface, 'radius')}
                </td>
                <td
                  className="px-2 py-1 text-right cursor-pointer hover:bg-blue-100"
                  onClick={() => handleCellClick(index, 'thickness', surface.thickness)}
                >
                  {renderCell(surface, 'thickness')}
                </td>
                <td
                  className="px-2 py-1 cursor-pointer hover:bg-blue-100"
                  onClick={() => handleCellClick(index, 'material', surface.material)}
                >
                  {renderCell(surface, 'material')}
                </td>
                <td
                  className="px-2 py-1 text-right cursor-pointer hover:bg-blue-100"
                  onClick={() => handleCellClick(index, 'conic', surface.conic)}
                >
                  {renderCell(surface, 'conic')}
                </td>
                <td
                  className="px-2 py-1 text-right cursor-pointer hover:bg-blue-100"
                  onClick={() => handleCellClick(index, 'semiDiameter', surface.semiDiameter)}
                >
                  {renderCell(surface, 'semiDiameter')}
                </td>
                <td className="px-2 py-1 text-center">
                  {index !== 0 && index !== surfaces.length - 1 && (
                    <button
                      onClick={() => deleteSurface(index)}
                      className="text-red-400 hover:text-red-600 text-xs"
                      title="Delete surface"
                    >
                      X
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      
      <div className="bg-gray-50 px-3 py-2 border-t border-gray-200 text-xs text-gray-500">
        <div className="flex gap-4">          <span><strong>V</strong> = Variable (optimize)</span>
          <span><strong>R</strong> = Radius</span>
          <span><strong>T</strong> = Thickness</span>
          <span className="text-yellow-600"><strong>Yellow</strong> = Stop</span>
        </div>
      </div>
    </div>
  );
}
