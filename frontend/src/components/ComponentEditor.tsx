/**
 * Component Editor Panel.
 *
 * Displays a list of optical components and allows the user to:
 * - Select a component
 * - Edit its properties (position, focal length, aperture, etc.)
 * - Add a new lens
 * - Remove a component
 *
 * Also allows editing of object properties, image plane position,
 * and analysis settings.
 */

import type {
  OpticalSystem,
  OpticalComponent,
  ThinLens,
} from "../types";
import { toMM } from "../types";

interface ComponentEditorProps {
  system: OpticalSystem;
  selectedComponent: OpticalComponent | null;
  selectedComponentId: string | null;
  onSelectComponent: (id: string | null) => void;
  onUpdateComponent: (id: string, field: string, value: number | string) => void;
  onUpdateObject: (field: string, value: number) => void;
  onUpdateImagePlane: (position: number) => void;
  onUpdateAnalysisSettings: (field: string, value: number | string[]) => void;
  onAddLens: () => void;
  onRemoveComponent: (id: string) => void;
}

export function ComponentEditor({
  system,
  selectedComponent,
  selectedComponentId,
  onSelectComponent,
  onUpdateComponent,
  onUpdateObject,
  onUpdateImagePlane,
  onUpdateAnalysisSettings,
  onAddLens,
  onRemoveComponent,
}: ComponentEditorProps) {
  const formatLensField = (label: string, field: string, value: number) => {
    return (
      <div key={field} className="mb-3">
        <label className="block text-sm font-medium text-gray-700 mb-1">
          {label} (mm)
        </label>
        <input
          type="number"
          step="0.1"
          value={toMM(value)}
          onChange={(e) => {
            const val = parseFloat(e.target.value);
            onUpdateComponent(selectedComponent!.id, field, val / 1000);
          }}
          className="w-full px-2 py-1 border border-gray-300 rounded text-sm"
        />
      </div>
    );
  };

  return (
    <div className="p-4">
      <h2 className="text-lg font-semibold text-gray-800 mb-4">
        Optical System Editor
      </h2>

      {/* Object Properties */}
      <div className="mb-4 p-3 bg-gray-50 rounded border">
        <h3 className="text-sm font-medium text-gray-700 mb-2">Object</h3>
        <div className="mb-2">
          <label className="block text-xs text-gray-600 mb-1">Position (mm)</label>
          <input
            type="number" step="1"
            value={toMM(system.object.position)}
            onChange={(e) => onUpdateObject("position", parseFloat(e.target.value) / 1000)}
            className="w-full px-2 py-1 border border-gray-300 rounded text-sm"
          />
        </div>
        <div className="mb-2">
          <label className="block text-xs text-gray-600 mb-1">Height (mm)</label>
          <input
            type="number" step="0.1"
            value={toMM(system.object.height)}
            onChange={(e) => onUpdateObject("height", parseFloat(e.target.value) / 1000)}
            className="w-full px-2 py-1 border border-gray-300 rounded text-sm"
          />
        </div>
      </div>

      {/* Components List */}
      <div className="mb-4">
        <div className="flex justify-between items-center mb-2">
          <h3 className="text-sm font-medium text-gray-700">Components</h3>
          <button
            onClick={onAddLens}
            className="px-2 py-1 bg-optical-600 text-white text-xs rounded hover:bg-optical-700"
          >
            + Add Lens
          </button>
        </div>
        <div className="space-y-1">
          {system.components.map((comp) => {
            const isSelected = comp.id === selectedComponentId;
            const isLens = comp.type === "thin_lens";
            return (
              <div
                key={comp.id}
                onClick={() => onSelectComponent(comp.id)}
                className={`p-2 border rounded cursor-pointer text-sm transition-colors ${
                  isSelected ? "border-optical-500 bg-optical-50" : "border-gray-200 hover:border-gray-300"
                }`}
              >
                <div className="flex justify-between items-center">
                  <span className="font-medium">{comp.id} ({comp.type})</span>
                  <button
                    onClick={(e) => { e.stopPropagation(); onRemoveComponent(comp.id); }}
                    className="text-red-500 hover:text-red-700 text-xs"
                  >
                    ✕
                  </button>
                </div>
                {isLens && (
                  <div className="text-xs text-gray-500 mt-1">
                    f={toMM((comp as ThinLens).focal_length).toFixed(0)}mm,
                    D={toMM((comp as ThinLens).aperture_diameter).toFixed(0)}mm
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Component Properties */}
      {selectedComponent && (
        <div className="mb-4 p-3 bg-gray-50 rounded border">
          <h3 className="text-sm font-medium text-gray-700 mb-2">
            Properties: {selectedComponent.id}
          </h3>
          <div className="mb-2">
            <label className="block text-xs text-gray-600 mb-1">Position (mm)</label>
            <input
              type="number" step="1"
              value={toMM(selectedComponent.position)}
              onChange={(e) => onUpdateComponent(selectedComponent.id, "position", parseFloat(e.target.value) / 1000)}
              className="w-full px-2 py-1 border border-gray-300 rounded text-sm"
            />
          </div>
          {selectedComponent.type === "thin_lens" && (
            <>
              {formatLensField("Focal Length", "focal_length", (selectedComponent as ThinLens).focal_length)}
              {formatLensField("Aperture Diameter", "aperture_diameter", (selectedComponent as ThinLens).aperture_diameter)}
              <div className="mb-3">
                <label className="block text-xs text-gray-600 mb-1">Material</label>
                <select
                  value={(selectedComponent as ThinLens).material}
                  onChange={(e) => onUpdateComponent(selectedComponent.id, "material", e.target.value)}
                  className="w-full px-2 py-1 border border-gray-300 rounded text-sm"
                >
                  <option value="N-BK7">N-BK7</option>
                  <option value="N-SF2">N-SF2</option>
                  <option value="N-SF5">N-SF5</option>
                  <option value="N-SF11">N-SF11</option>
                  <option value="FusedSilica">Fused Silica</option>
                </select>
              </div>
            </>
          )}
        </div>
      )}

      {/* Image Plane */}
      <div className="mb-4 p-3 bg-gray-50 rounded border">
        <h3 className="text-sm font-medium text-gray-700 mb-2">Image Plane</h3>
        <div className="mb-2">
          <label className="block text-xs text-gray-600 mb-1">Position (mm)</label>
          <input
            type="number" step="1"
            value={toMM(system.image_plane.position)}
            onChange={(e) => onUpdateImagePlane(parseFloat(e.target.value) / 1000)}
            className="w-full px-2 py-1 border border-gray-300 rounded text-sm"
          />
        </div>
      </div>

      {/* Analysis Settings */}
      <div className="mb-4 p-3 bg-gray-50 rounded border">
        <h3 className="text-sm font-medium text-gray-700 mb-2">Analysis Settings</h3>
        <div className="mb-2">
          <label className="block text-xs text-gray-600 mb-1">Number of Rays</label>
          <input
            type="number" min="1" max="101"
            value={system.analysis_settings.num_rays}
            onChange={(e) => onUpdateAnalysisSettings("num_rays", parseInt(e.target.value))}
            className="w-full px-2 py-1 border border-gray-300 rounded text-sm"
          />
        </div>
        <div className="mb-2">
          <label className="block text-xs text-gray-600 mb-1">Aperture Fraction</label>
          <input
            type="range" min="0" max="1" step="0.05"
            value={system.analysis_settings.aperture_fraction}
            onChange={(e) => onUpdateAnalysisSettings("aperture_fraction", parseFloat(e.target.value))}
            className="w-full"
          />
          <span className="text-xs text-gray-500">
            {Math.round(system.analysis_settings.aperture_fraction * 100)}%
          </span>
        </div>
      </div>
    </div>
  );
}
