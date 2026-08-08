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
} from "./types";
import { getDefaultSystem, traceRays, analyzeSystem } from "./api";
import { OpticalBench } from "./components/OpticalBench";
import { ComponentEditor } from "./components/ComponentEditor";
import { AnalysisPanel } from "./components/AnalysisPanel";
import { SpotDiagram } from "./components/SpotDiagram";

function App() {
  // Application state
  const [system, setSystem] = useState<OpticalSystem | null>(null);
  const [rayResult, setRayResult] = useState<RayTraceResult | null>(null);
  const [analysis, setAnalysis] = useState<AnalysisResult | null>(null);
  const [selectedComponentId, setSelectedComponentId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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
        <h1 className="text-2xl font-bold">AI Optical Design Engineer</h1>
        <p className="text-sm opacity-80">
          Local-first optical design and ray-tracing simulator
        </p>
      </header>

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Panel: Component Editor */}
        <div className="w-80 bg-white border-r border-gray-200 overflow-y-auto">
          <ComponentEditor
            system={system}
            selectedComponent={selectedComponent ?? null}
            selectedComponentId={selectedComponentId}
            onSelectComponent={setSelectedComponentId}
            onUpdateComponent={updateComponent}
            onUpdateObject={updateObject}
            onUpdateImagePlane={updateImagePlane}
            onUpdateAnalysisSettings={updateAnalysisSettings}
            onAddLens={addLens}
            onRemoveComponent={removeComponent}
          />
        </div>

        {/* Center: Optical Bench */}
        <div className="flex-1 overflow-auto">
          <OpticalBench
            system={system}
            rayResult={rayResult}
            analysis={analysis}
          />
        </div>

        {/* Right Panel: Analysis & Spot Diagram */}
        <div className="w-80 bg-white border-l border-gray-200 overflow-y-auto">
          <AnalysisPanel analysis={analysis} system={system} />
          <SpotDiagram analysis={analysis} />
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
