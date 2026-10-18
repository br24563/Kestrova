/**
 * Ghost Analysis Panel Component.
 *
 * Displays ghost reflection analysis results.
 */

import { useEffect, useState } from 'react';
import type { OpticalSystem } from '../../types';
import { analyzeGhosts } from '../../api';

interface GhostAnalysisPanelProps {
  system: OpticalSystem;
}

interface GhostResult {
  surfaces: number[];
  reflection_count: number;
  relative_intensity: number;
  image_position_offset: number;
  is_in_field: boolean;
  description: string;
}

export function GhostAnalysisPanel({ system }: GhostAnalysisPanelProps) {
  const [ghosts, setGhosts] = useState<GhostResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nReflections, setNReflections] = useState(2);
  
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    
    analyzeGhosts(system, nReflections)
      .then(result => {
        if (!cancelled) setGhosts(result.ghosts || []);
      })
      .catch(err => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    
    return () => { cancelled = true; };
  }, [system, nReflections]);
  
  const formatIntensity = (intensity: number) => {
    if (intensity < 0.0001) return (intensity * 10000).toFixed(2) + '% x1e-4';
    return (intensity * 100).toFixed(2) + '%';
  };

  return (
    <div className="p-4 border-t border-gray-200">
      <div className="flex justify-between items-center mb-3">
        <h3 className="text-sm font-semibold text-gray-700">Ghost Reflection Analysis</h3>
        <select
          value={nReflections}
          onChange={(e) => setNReflections(parseInt(e.target.value))}
          className="text-xs border border-gray-200 rounded px-2 py-1"
        >
          <option value={1}>Single reflections</option>
          <option value={2}>Double reflections</option>
        </select>
      </div>
      
      {loading && <p className="text-xs text-gray-500">Analyzing...</p>}
      {error && <p className="text-xs text-red-500">{error}</p>}
      
      {!loading && !error && ghosts.length === 0 && (
        <p className="text-xs text-gray-500">No significant ghost reflections found.</p>
      )}
      
      {!loading && ghosts.length > 0 && (
        <div className="space-y-2">
          <div className="text-xs text-gray-600">{ghosts.length} ghost path(s) found</div>
          <div className="max-h-48 overflow-y-auto space-y-1">
            {ghosts.map((ghost, i) => (
              <div
                key={i}
                className={`p-2 rounded text-xs border ${
                  ghost.is_in_field
                    ? 'bg-red-50 border-red-200'
                    : 'bg-gray-50 border-gray-200'
                }`}
              >
                <div className="flex justify-between items-start">
                  <div>
                    <div className="font-medium text-gray-700">
                      {ghost.description}
                    </div>
                    <div className="text-gray-500">
                      {ghost.reflection_count}x reflection | Intensity: {formatIntensity(ghost.relative_intensity)}
                    </div>
                  </div>
                  {ghost.is_in_field && (
                    <span className="px-1.5 py-0.5 bg-red-100 text-red-700 rounded text-xs">
                      In Field
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
