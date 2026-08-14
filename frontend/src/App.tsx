/**
 * Main application component for the AI Optical Design Engineer.
 *
 * This component manages the application state and renders the
 * optical system editor, optical bench visualization, analysis panel,
 * and spot diagram.
 */

import { useState, useEffect, useCallback } from "react";
import type {
  OpticalSystem,
  OpticalComponent,
  ThinLens,
  RayTraceResult,
  AnalysisResult,
  LengthUnit,
} from "./types";
import { getDefaultSystem, traceRays, analyzeSystem } from "./api";
import { OpticalBench } from "./components/OpticalBench";
import { ComponentEditor } from "./components/ComponentEditor";
import { AnalysisPanel } from "./components/AnalysisPanel";
import { SpotDiagram } from "./components/SpotDiagram";
import { DEFAULT_LENGTH_UNIT, LENGTH_UNIT_LABELS } from "./types";

const STORAGE_KEY = "ai-optical-design-engineer-system";

function App() {
  // Application state
  const [system, setSystem] = useState<OpticalSystem | null>(null);
  const [rayResult, setRayResult] = useState<RayTraceResult | null>(null);
  const [analysis, setAnalysis] = useState<AnalysisResult | null>(null);
  const [selectedComponentId, setSelectedComponentId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [displayUnit, setDisplayUnit] = useState<LengthUnit>(DEFAULT_LENGTH_UNIT);

  // Load the default system on mount
  useEffect(() => {
    loadDefaultSystem();
  }, []);

  // Trace rays and analyze whenever the system changes
  useEffect(() => {
    if (system) {
      updateSimulation();
    }
  }, [system]);

  const loadDefaultSystem = async () => {
    try {
      setLoading(true);
      const response = await getDefaultSystem();
      setSystem(response.system);
      setSelectedComponentId(response.system.components[0]?.id ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load system");
    } finally {
      setLoading(false);
    }
  };

  const updateSimulation = useCallback(async () => {
    if (!system) return;

    try {
      // Trace rays
      const traceResult = await traceRays(
        system,
        system.analysis_settings.num_rays,
        system.analysis_settings.aperture_fraction,
      );
      setRayResult(traceResult);

      // Analyze system
      const analysisResult = await analyzeSystem(
        system,
        system.analysis_settings.num_rays,
        system.analysis_settings.aperture_fraction,
      );
      setAnalysis(analysisResult);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Simulation failed");
    }
  }, [system]);

  // Update a component's property
  const updateComponent = (id: string, field: string, value: number | string) => {
    if (!system) return;

    const newComponents = system.components.map((comp) => {
      if (comp.id === id) {
        return { ...comp, [field]: value };
      }
      return comp;
    });

    setSystem({ ...system, components: newComponents });
  };

  // Update object properties
  const updateObject = (field: string, value: number) => {
    if (!system) return;
    setSystem({
      ...system,
      object: { ...system.object, [field]: value },
    });
  };

  // Update image plane position
  const updateImagePlane = (position: number) => {
    if (!system) return;
    setSystem({
      ...system,
      image_plane: { position },
    });
  };

  // Update analysis settings
  const updateAnalysisSettings = (field: string, value: number | string[]) => {
    if (!system) return;
    setSystem({
      ...system,
      analysis_settings: {
        ...system.analysis_settings,
        [field]: value,
      },
    });
  };

  // Add a new lens
  const addLens = () => {
    if (!system) return;
    const newLens: ThinLens = {
      type: "thin_lens",
      id: `lens_${system.components.length + 1}`,
      position: 0.200,
      focal_length: 0.050,
      aperture_diameter: 0.025,
      material: "N-BK7",
    };
    setSystem({
      ...system,
      components: [...system.components, newLens],
    });
  };

  // Remove a component
  const removeComponent = (id: string) => {
    if (!system) return;
    setSystem({
      ...system,
      components: system.components.filter((c) => c.id !== id),
    });
    if (selectedComponentId === id) {
      setSelectedComponentId(null);
    }
  };

  // Reorder a component (move up or down in the list)
  const reorderComponent = (id: string, direction: "up" | "down") => {
    if (!system) return;
    const index = system.components.findIndex((c) => c.id === id);
    if (index === -1) return;
    const newIndex = direction === "up" ? index - 1 : index + 1;
    if (newIndex < 0 || newIndex >= system.components.length) return;

    const newComponents = [...system.components];
    [newComponents[index], newComponents[newIndex]] = [newComponents[newIndex], newComponents[index]];
    setSystem({ ...system, components: newComponents });
  };

  // Save the current system to localStorage
  const saveSystem = () => {
    if (!system) return;
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(system));
      setSaveMessage("System saved!");
      setTimeout(() => setSaveMessage(null), 2000);
    } catch (err) {
      setSaveMessage("Failed to save system");
      setTimeout(() => setSaveMessage(null), 2000);
    }
  };

  // Load a saved system from localStorage
  const loadSavedSystem = () => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (!saved) {
        setSaveMessage("No saved system found");
        setTimeout(() => setSaveMessage(null), 2000);
        return;
      }
      const parsed = JSON.parse(saved) as OpticalSystem;
      setSystem(parsed);
      setSelectedComponentId(parsed.components[0]?.id ?? null);
      setSaveMessage("System loaded!");
      setTimeout(() => setSaveMessage(null), 2000);
    } catch (err) {
      setSaveMessage("Failed to load system");
      setTimeout(() => setSaveMessage(null), 2000);
    }
  };

  // Get the selected component
  const selectedComponent = system?.components.find(
    (c) => c.id === selectedComponentId,
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="text-xl">Loading AI Optical Design Engineer...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="text-red-500">Error: {error}</div>
      </div>
    );
  }

  if (!system) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div>No system loaded.</div>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col bg-gray-50">
      {/* Header */}
      <header className="bg-gradient-to-r from-optical-700 to-optical-800 text-white p-4 shadow-md">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">AI Optical Design Engineer</h1>
            <p className="text-sm opacity-80">
              Local-first optical design and ray-tracing simulator
            </p>
          </div>
          <div className="flex items-center gap-2">
            <label className="text-xs opacity-80">Units:</label>
            <select
              value={displayUnit}
              onChange={(e) => setDisplayUnit(e.target.value as LengthUnit)}
              className="px-2 py-1.5 bg-white/20 hover:bg-white/30 rounded text-sm font-medium text-white border border-white/30"
            >
              {(Object.keys(LENGTH_UNIT_LABELS) as LengthUnit[]).map((u) => (
                <option key={u} value={u} className="text-gray-800">
                  {LENGTH_UNIT_LABELS[u]}
                </option>
              ))}
            </select>
            <button
              onClick={saveSystem}
              className="px-3 py-1.5 bg-white/20 hover:bg-white/30 rounded text-sm font-medium transition-colors"
            >
              Save
            </button>
            <button
              onClick={loadSavedSystem}
              className="px-3 py-1.5 bg-white/20 hover:bg-white/30 rounded text-sm font-medium transition-colors"
            >
              Load
            </button>
            {saveMessage && (
              <span className="text-xs bg-white/20 px-2 py-1 rounded">{saveMessage}</span>
            )}
          </div>
        </div>
      </header>

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Panel: Component Editor */}
        <div className="w-80 bg-white border-r border-gray-200 overflow-y-auto">
          <ComponentEditor
            system={system}
            selectedComponent={selectedComponent ?? null}
            selectedComponentId={selectedComponentId}
            displayUnit={displayUnit}
            onSelectComponent={setSelectedComponentId}
            onUpdateComponent={updateComponent}
            onUpdateObject={updateObject}
            onUpdateImagePlane={updateImagePlane}
            onUpdateAnalysisSettings={updateAnalysisSettings}
            onAddLens={addLens}
            onRemoveComponent={removeComponent}
            onReorderComponent={reorderComponent}
          />
        </div>

        {/* Center: Optical Bench */}
        <div className="flex-1 overflow-auto">
          <OpticalBench
            system={system}
            rayResult={rayResult}
            analysis={analysis}
            displayUnit={displayUnit}
          />
        </div>

        {/* Right Panel: Analysis & Spot Diagram */}
        <div className="w-80 bg-white border-l border-gray-200 overflow-y-auto">
          <AnalysisPanel analysis={analysis} system={system} displayUnit={displayUnit} />
          <SpotDiagram analysis={analysis} displayUnit={displayUnit} />
        </div>
      </div>

      {/* Footer */}
      <footer className="bg-gray-100 text-gray-600 text-xs p-2 text-center">
        AI Optical Design Engineer v0.1.0 — MVP: Two-Lens Ray Tracer
      </footer>
    </div>
  );
}

export default App;
