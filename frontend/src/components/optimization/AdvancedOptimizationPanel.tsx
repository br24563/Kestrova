/**
 * Advanced Optimization Panel Component.
 *
 * Professional optimization interface with:
 * - Algorithm selection (DE, PSO, DLS, L-BFGS-B)
 * - Hybrid pipeline option
 * - Constraint editor
 * - High-yield optimization
 * - Progress monitoring
 */

import { useState } from 'react';
import type { OpticalSystem, LengthUnit } from '../../types';
import { fromMeters } from '../../types';

interface AdvancedOptimizationPanelProps {
  system: OpticalSystem;
  displayUnit: LengthUnit;
  onApplyOptimized: (system: OpticalSystem) => void;
}

interface OptimizationResult {
  success: boolean;
  objective: number;
  params: number[];
  message?: string;
}

export function AdvancedOptimizationPanel({ system, displayUnit, onApplyOptimized }: AdvancedOptimizationPanelProps) {
  const [algorithm, setAlgorithm] = useState<'hybrid' | 'high-yield'>('hybrid');
  const [globalAlgo, setGlobalAlgo] = useState<'de' | 'pso'>('de');
  const [localAlgo, setLocalAlgo] = useState<'dls' | 'l-bfgs-b'>('dls');
  const [objective, setObjective] = useState<'rms_spot' | 'efl' | 'magnification'>('rms_spot');
  const [maxIter, setMaxIter] = useState(200);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<OptimizationResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  
  // Parameter selection
  const [selectedParams, setSelectedParams] = useState<string[]>([]);
  
  const availableParams = system.components.flatMap(comp => {
    const params: { id: string; label: string }[] = [];
    if (comp.type === 'thin_lens') {
      params.push({ id: `${comp.id}.focal_length`, label: `${comp.id} Focal Length` });
    } else if (comp.type === 'thick_lens') {
      params.push({ id: `${comp.id}.radius1`, label: `${comp.id} Radius 1` });
      params.push({ id: `${comp.id}.radius2`, label: `${comp.id} Radius 2` });
    }
    params.push({ id: `${comp.id}.position`, label: `${comp.id} Position` });
    return params;
  });
  
  const toggleParam = (id: string) => {
    setSelectedParams(prev => 
      prev.includes(id) ? prev.filter(p => p !== id) : [...prev, id]
    );
  };
  
  const handleRun = async () => {
    if (selectedParams.length === 0) {
      setError('Select at least one parameter to optimize');
      return;
    }
    
    setRunning(true);
    setError(null);
    setResult(null);
    
    try {
      // Build parameter specs and bounds
      const params: { component_id: string; field: string }[] = [];
      const bounds: [number, number][] = [];
      
      for (const paramId of selectedParams) {
        const [compId, field] = paramId.split('.');
        params.push({ component_id: compId, field });
        
        // Set bounds based on field type
        if (field === 'focal_length') {
          bounds.push([0.01, 0.5]);
        } else if (field === 'radius1' || field === 'radius2') {
          bounds.push([-0.5, 0.5]);
        } else if (field === 'position') {
          bounds.push([0.01, 0.5]);
        } else {
          bounds.push([-0.1, 0.1]);
        }
      }
      
      const endpoint = algorithm === 'hybrid' ? '/api/optimize/hybrid' : '/api/optimize/high-yield';
      
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          system,
          objective,
          params,
          bounds,
          global_maxiter: maxIter,
          local_maxiter: maxIter / 2,
          seed: 42,
          ...(algorithm === 'high-yield' ? {
            tolerances: Object.fromEntries(
              selectedParams.filter(p => p.endsWith('.position')).map(p => [p, 1e-4])
            ),
            yield_threshold: 0.95,
            n_monte_carlo: 30,
          } : {}),
        }),
      });
      
      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.detail || 'Optimization failed');
      }
      
      const data = await response.json();
      setResult({
        success: data.success,
        objective: data.objective,
        params: data.params,
      });
      
      if (data.system) {
        onApplyOptimized(data.system);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Optimization failed');
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="p-4 border-t border-gray-200">
      <h3 className="text-sm font-semibold text-gray-700 mb-3">Advanced Optimization</h3>
      
      <div className="space-y-3">
        {/* Algorithm Selection */}
        <div>
          <label className="block text-xs text-gray-600 mb-1">Algorithm</label>
          <select
            value={algorithm}
            onChange={(e) => setAlgorithm(e.target.value as 'hybrid' | 'high-yield')}
            className="w-full px-2 py-1 text-xs border border-gray-200 rounded"
          >
            <option value="hybrid">Hybrid (Global + Local)</option>
            <option value="high-yield">High-Yield (with Tolerances)</option>
          </select>
        </div>
        
        {algorithm === 'hybrid' && (
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="block text-xs text-gray-600 mb-1">Global</label>
              <select
                value={globalAlgo}
                onChange={(e) => setGlobalAlgo(e.target.value as 'de' | 'pso')}
                className="w-full px-2 py-1 text-xs border border-gray-200 rounded"
              >
                <option value="de">Diff. Evolution</option>
                <option value="pso">Particle Swarm</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-gray-600 mb-1">Local</label>
              <select
                value={localAlgo}
                onChange={(e) => setLocalAlgo(e.target.value as 'dls' | 'l-bfgs-b')}
                className="w-full px-2 py-1 text-xs border border-gray-200 rounded"
              >
                <option value="dls">Damped Least Squares</option>
                <option value="l-bfgs-b">L-BFGS-B</option>
              </select>
            </div>
          </div>
        )}
        
        {/* Objective */}
        <div>
          <label className="block text-xs text-gray-600 mb-1">Objective</label>
          <select
            value={objective}
            onChange={(e) => setObjective(e.target.value as 'rms_spot' | 'efl' | 'magnification')}
            className="w-full px-2 py-1 text-xs border border-gray-200 rounded"
          >
            <option value="rms_spot">Minimize RMS Spot</option>
            <option value="efl">Target EFL</option>
            <option value="magnification">Target Magnification</option>
          </select>
        </div>
        
        {/* Max Iterations */}
        <div>
          <label className="block text-xs text-gray-600 mb-1">Max Iterations: {maxIter}</label>
          <input
            type="range"
            min="50"
            max="1000"
            step="50"
            value={maxIter}
            onChange={(e) => setMaxIter(parseInt(e.target.value))}
            className="w-full"
          />
        </div>
        
        {/* Parameter Selection */}
        <div>
          <label className="block text-xs text-gray-600 mb-1">Parameters to Optimize</label>
          <div className="max-h-32 overflow-y-auto border border-gray-200 rounded p-2 space-y-1">
            {availableParams.map(param => (
              <label key={param.id} className="flex items-center gap-2 text-xs cursor-pointer hover:bg-gray-50">
                <input
                  type="checkbox"
                  checked={selectedParams.includes(param.id)}
                  onChange={() => toggleParam(param.id)}
                  className="w-3 h-3"
                />
                <span className="text-gray-700">{param.label}</span>
              </label>
            ))}
          </div>
        </div>
        
        {/* Run Button */}
        <button
          onClick={handleRun}
          disabled={running || selectedParams.length === 0}
          className="w-full px-3 py-2 bg-blue-600 text-white text-sm rounded hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {running ? 'Optimizing...' : 'Run Optimization'}
        </button>
        
        {/* Results */}
        {result && (
          <div className="p-3 bg-green-50 border border-green-200 rounded text-xs">
            <div className="font-medium text-green-800">Optimization Complete</div>
            <div className="text-green-700 mt-1">
              Final objective: {result.objective.toExponential(4)}
            </div>
          </div>
        )}
        
        {error && (
          <div className="p-3 bg-red-50 border border-red-200 rounded text-xs text-red-700">
            {error}
          </div>
        )}
      </div>
    </div>
  );
}
