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
  SphericalSurface,
  ThickLens,
  ApertureStop,
  Mirror,
  RayTraceResult,
  AnalysisResult,
  LengthUnit,
} from "./types";
import {
  getDefaultSystem, traceRays, analyzeSystem,
  listSystems, saveSystem, loadSystem, deleteSystem,
  type SystemMetadata,
} from "./api";
import { OpticalBench } from "./components/OpticalBench";
import { ComponentEditor } from "./components/ComponentEditor";
import { AnalysisPanel } from "./components/AnalysisPanel";
import { SpotDiagram } from "./components/SpotDiagram";
import { AIChatPanel } from "./components/AIChatPanel";
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
  const [projects, setProjects] = useState<SystemMetadata[]>([]);
  const [projectName, setProjectName] = useState<string>("");

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

  // Add a new spherical surface
  const addSurface = () => {
    if (!system) return;
    const newSurface: SphericalSurface = {
      type: "spherical_surface",
      id: `surface_${system.components.length + 1}`,
      position: 0.200,
      radius: 0.100,
      thickness: 0.005,
      material: "N-BK7",
    };
    setSystem({
      ...system,
      components: [...system.components, newSurface],
    });
  };

  // Add a new thick lens
  const addThickLens = () => {
    if (!system) return;
    const newThickLens: ThickLens = {
      type: "thick_lens",
      id: `thick_lens_${system.components.length + 1}`,
      position: 0.200,
      radius1: 0.100,
      radius2: -0.100,
      thickness: 0.010,
      aperture_diameter: 0.025,
      material: "N-BK7",
    };
    setSystem({
      ...system,
      components: [...system.components, newThickLens],
    });
  };

  // Add a new aperture stop
  const addAperture = () => {
    if (!system) return;
    const newAperture: ApertureStop = {
      type: "aperture",
      id: `aperture_${system.components.length + 1}`,
      position: 0.200,
      diameter: 0.025,
    };
    setSystem({
      ...system,
      components: [...system.components, newAperture],
    });
  };

  // Add a new mirror
  const addMirror = () => {
    if (!system) return;
    const newMirror: Mirror = {
      type: "mirror",
      id: `mirror_${system.components.length + 1}`,
      position: 0.200,
      width: 0.050,
    };
    setSystem({
      ...system,
      components: [...system.components, newMirror],
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
  const saveToLocalStorage = () => {
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
  const loadFromLocalStorage = () => {
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

  // Refresh the list of saved projects
  const refreshProjects = useCallback(async () => {
    try {
      const list = await listSystems();
      setProjects(list);
    } catch (err) {
      setSaveMessage(err instanceof Error ? err.message : "Failed to list projects");
      setTimeout(() => setSaveMessage(null), 2000);
    }
  }, []);

  // Save the current system as a named project in the database
  const saveProject = async () => {
    if (!system || !projectName.trim()) {
      setSaveMessage("Enter a project name to save");
      setTimeout(() => setSaveMessage(null), 2000);
      return;
    }
    try {
      await saveSystem(projectName.trim(), system);
      setProjectName("");
      setSaveMessage("Project saved!");
      setTimeout(() => setSaveMessage(null), 2000);
      refreshProjects();
    } catch (err) {
      setSaveMessage(err instanceof Error ? err.message : "Failed to save project");
      setTimeout(() => setSaveMessage(null), 2000);
    }
  };

  // Load a saved project from the database
  const loadProject = async (id: number) => {
    try {
      const saved = await loadSystem(id);
      const parsed = JSON.parse(saved.system_json) as OpticalSystem;
      setSystem(parsed);
      setSelectedComponentId(parsed.components[0]?.id ?? null);
      setSaveMessage("Project loaded!");
      setTimeout(() => setSaveMessage(null), 2000);
    } catch (err) {
      setSaveMessage(err instanceof Error ? err.message : "Failed to load project");
      setTimeout(() => setSaveMessage(null), 2000);
    }
  };

  // Delete a saved project from the database
  const deleteProject = async (id: number) => {
    try {
      await deleteSystem(id);
      setSaveMessage("Project deleted!");
      setTimeout(() => setSaveMessage(null), 2000);
      refreshProjects();
    } catch (err) {
      setSaveMessage(err instanceof Error ? err.message : "Failed to delete project");
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
              onClick={saveToLocalStorage}
              className="px-3 py-1.5 bg-white/20 hover:bg-white/30 rounded text-sm font-medium transition-colors"
            >
              Save
            </button>
            <button
              onClick={loadFromLocalStorage}
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
        {/* Left Panel: Component Editor + Projects */}
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
            onAddSurface={addSurface}
            onAddThickLens={addThickLens}
            onAddAperture={addAperture}
            onAddMirror={addMirror}
            onRemoveComponent={removeComponent}
            onReorderComponent={reorderComponent}
          />

          {/* AI Chat Panel */}
          <AIChatPanel system={system} onSystemUpdate={setSystem} />

          {/* Projects Panel */}
          <div className="p-4 border-t border-gray-200">
            <div className="flex justify-between items-center mb-2">
              <h3 className="text-sm font-medium text-gray-700">Projects</h3>
              <button
                onClick={refreshProjects}
                className="text-xs text-optical-600 hover:text-optical-700"
              >
                Refresh
              </button>
            </div>
            <div className="flex gap-1 mb-3">
              <input
                type="text"
                value={projectName}
                onChange={(e) => setProjectName(e.target.value)}
                placeholder="Project name"
                className="flex-1 px-2 py-1 border border-gray-300 rounded text-sm"
              />
              <button
                onClick={saveProject}
                className="px-2 py-1 bg-optical-600 text-white text-xs rounded hover:bg-optical-700"
              >
                Save
              </button>
            </div>
            {projects.length === 0 ? (
              <p className="text-xs text-gray-500">No saved projects.</p>
            ) : (
              <div className="space-y-1">
                {projects.map((p) => (
                  <div
                    key={p.id}
                    className="flex justify-between items-center p-2 border border-gray-200 rounded text-sm"
                  >
                    <button
                      onClick={() => loadProject(p.id)}
                      className="text-left font-medium hover:text-optical-600"
                    >
                      {p.name}
                    </button>
                    <button
                      onClick={() => deleteProject(p.id)}
                      className="text-red-500 hover:text-red-700 text-xs"
                    >
                      ✕
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
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
