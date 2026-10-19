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
  SphericalSurface,
  ThickLens,
  ApertureStop,
  Mirror,
  LengthUnit,
} from "../types";
import { fromMeters, toMeters, LENGTH_UNIT_LABELS } from "../types";

interface ComponentEditorProps {
  system: OpticalSystem;
  selectedComponent: OpticalComponent | null;
  selectedComponentId: string | null;
  displayUnit: LengthUnit;
  onSelectComponent: (id: string | null) => void;
  onUpdateComponent: (
    id: string,
    field: string,
    value: number | string,
  ) => void;
  onUpdateObject: (field: string, value: number) => void;
  onUpdateImagePlane: (position: number) => void;
  onUpdateAnalysisSettings: (field: string, value: number | string[]) => void;
  onAddLens: () => void;
  onAddSurface: () => void;
  onAddThickLens: () => void;
  onAddAperture: () => void;
  onAddMirror: () => void;
  onRemoveComponent: (id: string) => void;
  onReorderComponent: (id: string, direction: "up" | "down") => void;
}

export function ComponentEditor({
  system,
  selectedComponent,
  selectedComponentId,
  displayUnit,
  onSelectComponent,
  onUpdateComponent,
  onUpdateObject,
  onUpdateImagePlane,
  onUpdateAnalysisSettings,
  onAddLens,
  onAddSurface,
  onAddThickLens,
  onAddAperture,
  onAddMirror,
  onRemoveComponent,
  onReorderComponent,
}: ComponentEditorProps) {
  const unitLabel = LENGTH_UNIT_LABELS[displayUnit];

  const formatLensField = (label: string, field: string, value: number) => {
    return (
      <div key={field} className="mb-3">
        <label className="block text-sm font-medium text-gray-700 mb-1">
          {label} ({unitLabel})
        </label>
        <input
          type="number"
          step="any"
          value={fromMeters(value, displayUnit)}
          onChange={(e) => {
            const val = parseFloat(e.target.value);
            if (!isNaN(val)) {
              onUpdateComponent(
                selectedComponent!.id,
                field,
                toMeters(val, displayUnit),
              );
            }
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
          <label className="block text-xs text-gray-600 mb-1">
            Position ({unitLabel})
          </label>
          <input
            type="number"
            step="any"
            value={fromMeters(system.object.position, displayUnit)}
            onChange={(e) => {
              const val = parseFloat(e.target.value);
              if (!isNaN(val))
                onUpdateObject("position", toMeters(val, displayUnit));
            }}
            className="w-full px-2 py-1 border border-gray-300 rounded text-sm"
          />
        </div>
        <div className="mb-2">
          <label className="block text-xs text-gray-600 mb-1">
            Height ({unitLabel})
          </label>
          <input
            type="number"
            step="any"
            value={fromMeters(system.object.height, displayUnit)}
            onChange={(e) => {
              const val = parseFloat(e.target.value);
              if (!isNaN(val))
                onUpdateObject("height", toMeters(val, displayUnit));
            }}
            className="w-full px-2 py-1 border border-gray-300 rounded text-sm"
          />
        </div>
      </div>

      {/* Components List */}
      <div className="mb-4">
        <div className="flex justify-between items-center mb-2">
          <h3 className="text-sm font-medium text-gray-700">Components</h3>
          <div className="flex gap-1">
            <button
              onClick={onAddLens}
              className="px-2 py-1 bg-optical-600 text-white text-xs rounded hover:bg-optical-700"
            >
              + Lens
            </button>
            <button
              onClick={onAddSurface}
              className="px-2 py-1 bg-optical-600 text-white text-xs rounded hover:bg-optical-700"
            >
              + Surface
            </button>
            <button
              onClick={onAddThickLens}
              className="px-2 py-1 bg-optical-600 text-white text-xs rounded hover:bg-optical-700"
            >
              + Thick Lens
            </button>
            <button
              onClick={onAddAperture}
              className="px-2 py-1 bg-optical-600 text-white text-xs rounded hover:bg-optical-700"
            >
              + Aperture
            </button>
            <button
              onClick={onAddMirror}
              className="px-2 py-1 bg-optical-600 text-white text-xs rounded hover:bg-optical-700"
            >
              + Mirror
            </button>
          </div>
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
                  isSelected
                    ? "border-optical-500 bg-optical-50"
                    : "border-gray-200 hover:border-gray-300"
                }`}
              >
                <div className="flex justify-between items-center">
                  <span className="font-medium">
                    {comp.id} ({comp.type})
                  </span>
                  <div className="flex items-center gap-1">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onReorderComponent(comp.id, "up");
                      }}
                      className="text-gray-400 hover:text-gray-600 text-xs px-1"
                      title="Move up"
                    >
                      ↑
                    </button>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onReorderComponent(comp.id, "down");
                      }}
                      className="text-gray-400 hover:text-gray-600 text-xs px-1"
                      title="Move down"
                    >
                      ↓
                    </button>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onRemoveComponent(comp.id);
                      }}
                      className="text-red-500 hover:text-red-700 text-xs"
                    >
                      ✕
                    </button>
                  </div>
                </div>
                {isLens && (
                  <div className="text-xs text-gray-500 mt-1">
                    f=
                    {fromMeters(
                      (comp as ThinLens).focal_length,
                      displayUnit,
                    ).toFixed(1)}
                    {unitLabel}, D=
                    {fromMeters(
                      (comp as ThinLens).aperture_diameter,
                      displayUnit,
                    ).toFixed(1)}
                    {unitLabel}
                  </div>
                )}
                {comp.type === "spherical_surface" && (
                  <div className="text-xs text-gray-500 mt-1">
                    R=
                    {fromMeters(
                      (comp as SphericalSurface).radius,
                      displayUnit,
                    ).toFixed(1)}
                    {unitLabel}, t=
                    {fromMeters(
                      (comp as SphericalSurface).thickness,
                      displayUnit,
                    ).toFixed(1)}
                    {unitLabel}
                  </div>
                )}
                {comp.type === "thick_lens" && (
                  <div className="text-xs text-gray-500 mt-1">
                    R1=
                    {fromMeters(
                      (comp as ThickLens).radius1,
                      displayUnit,
                    ).toFixed(1)}
                    {unitLabel}, R2=
                    {fromMeters(
                      (comp as ThickLens).radius2,
                      displayUnit,
                    ).toFixed(1)}
                    {unitLabel}, t=
                    {fromMeters(
                      (comp as ThickLens).thickness,
                      displayUnit,
                    ).toFixed(1)}
                    {unitLabel}
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
            <label className="block text-xs text-gray-600 mb-1">
              Position ({unitLabel})
            </label>
            <input
              type="number"
              step="any"
              value={fromMeters(selectedComponent.position, displayUnit)}
              onChange={(e) => {
                const val = parseFloat(e.target.value);
                if (!isNaN(val))
                  onUpdateComponent(
                    selectedComponent.id,
                    "position",
                    toMeters(val, displayUnit),
                  );
              }}
              className="w-full px-2 py-1 border border-gray-300 rounded text-sm"
            />
          </div>
          {selectedComponent.type === "thin_lens" && (
            <>
              {formatLensField(
                "Focal Length",
                "focal_length",
                (selectedComponent as ThinLens).focal_length,
              )}
              {formatLensField(
                "Aperture Diameter",
                "aperture_diameter",
                (selectedComponent as ThinLens).aperture_diameter,
              )}
              <div className="mb-3">
                <label className="block text-xs text-gray-600 mb-1">
                  Material
                </label>
                <select
                  value={(selectedComponent as ThinLens).material}
                  onChange={(e) =>
                    onUpdateComponent(
                      selectedComponent.id,
                      "material",
                      e.target.value,
                    )
                  }
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
          {selectedComponent.type === "spherical_surface" && (
            <>
              {formatLensField(
                "Radius of Curvature",
                "radius",
                (selectedComponent as SphericalSurface).radius,
              )}
              {formatLensField(
                "Thickness",
                "thickness",
                (selectedComponent as SphericalSurface).thickness,
              )}
              <div className="mb-3">
                <label className="block text-xs text-gray-600 mb-1">
                  Material
                </label>
                <select
                  value={(selectedComponent as SphericalSurface).material}
                  onChange={(e) =>
                    onUpdateComponent(
                      selectedComponent.id,
                      "material",
                      e.target.value,
                    )
                  }
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
          {selectedComponent.type === "thick_lens" && (
            <>
              {formatLensField(
                "Radius 1",
                "radius1",
                (selectedComponent as ThickLens).radius1,
              )}
              {formatLensField(
                "Radius 2",
                "radius2",
                (selectedComponent as ThickLens).radius2,
              )}
              {formatLensField(
                "Thickness",
                "thickness",
                (selectedComponent as ThickLens).thickness,
              )}
              {formatLensField(
                "Aperture Diameter",
                "aperture_diameter",
                (selectedComponent as ThickLens).aperture_diameter,
              )}
              <div className="mb-3">
                <label className="block text-xs text-gray-600 mb-1">
                  Material
                </label>
                <select
                  value={(selectedComponent as ThickLens).material}
                  onChange={(e) =>
                    onUpdateComponent(
                      selectedComponent.id,
                      "material",
                      e.target.value,
                    )
                  }
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
          {selectedComponent.type === "aperture" && (
            <>
              {formatLensField(
                "Diameter",
                "diameter",
                (selectedComponent as ApertureStop).diameter,
              )}
            </>
          )}
          {selectedComponent.type === "mirror" && (
            <>
              {formatLensField(
                "Width",
                "width",
                (selectedComponent as Mirror).width,
              )}
              {formatLensField(
                "Radius of Curvature (0 = flat)",
                "radius",
                (selectedComponent as Mirror).radius ?? 0,
              )}
              <div className="mb-3">
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Conic Constant
                </label>
                <input
                  type="number"
                  step="any"
                  value={(selectedComponent as Mirror).conic ?? 0}
                  onChange={(e) => {
                    const val = parseFloat(e.target.value);
                    if (!isNaN(val))
                      onUpdateComponent(selectedComponent.id, "conic", val);
                  }}
                  className="w-full px-2 py-1 border border-gray-300 rounded text-sm"
                />
              </div>
            </>
          )}
        </div>
      )}

      {/* Image Plane */}
      <div className="mb-4 p-3 bg-gray-50 rounded border">
        <h3 className="text-sm font-medium text-gray-700 mb-2">Image Plane</h3>
        <div className="mb-2">
          <label className="block text-xs text-gray-600 mb-1">
            Position ({unitLabel})
          </label>
          <input
            type="number"
            step="any"
            value={fromMeters(system.image_plane.position, displayUnit)}
            onChange={(e) => {
              const val = parseFloat(e.target.value);
              if (!isNaN(val)) onUpdateImagePlane(toMeters(val, displayUnit));
            }}
            className="w-full px-2 py-1 border border-gray-300 rounded text-sm"
          />
        </div>
      </div>

      {/* Analysis Settings */}
      <div className="mb-4 p-3 bg-gray-50 rounded border">
        <h3 className="text-sm font-medium text-gray-700 mb-2">
          Analysis Settings
        </h3>
        <div className="mb-2">
          <label className="block text-xs text-gray-600 mb-1">
            Number of Rays
          </label>
          <input
            type="number"
            min="1"
            max="101"
            value={system.analysis_settings.num_rays}
            onChange={(e) =>
              onUpdateAnalysisSettings("num_rays", parseInt(e.target.value))
            }
            className="w-full px-2 py-1 border border-gray-300 rounded text-sm"
          />
        </div>
        <div className="mb-2">
          <label className="block text-xs text-gray-600 mb-1">
            Aperture Fraction
          </label>
          <input
            type="range"
            min="0"
            max="1"
            step="0.05"
            value={system.analysis_settings.aperture_fraction}
            onChange={(e) =>
              onUpdateAnalysisSettings(
                "aperture_fraction",
                parseFloat(e.target.value),
              )
            }
            className="w-full"
          />
          <span className="text-xs text-gray-500">
            {Math.round(system.analysis_settings.aperture_fraction * 100)}%
          </span>
        </div>
        <div className="mb-2">
          <label className="block text-xs text-gray-600 mb-1">
            Wavelength (nm)
          </label>
          <input
            type="number"
            min="380"
            max="780"
            step="1"
            value={Math.round(system.analysis_settings.wavelength * 1e9)}
            onChange={(e) =>
              onUpdateAnalysisSettings(
                "wavelength",
                parseFloat(e.target.value) / 1e9,
              )
            }
            className="w-full px-2 py-1 border border-gray-300 rounded text-sm"
          />
        </div>
        <div className="mb-2">
          <label className="block text-xs text-gray-600 mb-1">Ray Types</label>
          <div className="flex flex-wrap gap-2">
            {["chief", "marginal", "fill"].map((type) => (
              <label key={type} className="flex items-center gap-1 text-xs">
                <input
                  type="checkbox"
                  checked={system.analysis_settings.ray_types.includes(type)}
                  onChange={(e) => {
                    const current = system.analysis_settings.ray_types;
                    const updated = e.target.checked
                      ? [...current, type]
                      : current.filter((t) => t !== type);
                    onUpdateAnalysisSettings("ray_types", updated);
                  }}
                  className="rounded"
                />
                {type}
              </label>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
