/**
 * Merit Function Editor Component.
 *
 * Professional merit function editor for optical optimization.
 */

import { useState, useCallback } from 'react';

interface MeritOperand {
  id: number;
  type: string;
  target: number;
  weight: number;
  value: number;
  contribution: number;
  active: boolean;
  constraintMin: number | null;
  constraintMax: number | null;
}

interface MeritFunctionEditorProps {
  onMeritFunctionChange?: (operands: MeritOperand[]) => void;
}

let nextOperandId = 1;

const OPERAND_CATALOG = [
  { type: 'EFFL', description: 'Effective Focal Length', defaultTarget: 100 },
  { type: 'WFNO', description: 'Working F/number', defaultTarget: 2.8 },
  { type: 'SPHA', description: 'Spherical Aberration', defaultTarget: 0 },
  { type: 'COMA', description: 'Coma', defaultTarget: 0 },
  { type: 'ASTI', description: 'Astigmatism', defaultTarget: 0 },
  { type: 'DIST', description: 'Distortion', defaultTarget: 0 },
  { type: 'LAXC', description: 'Longitudinal Axial Color', defaultTarget: 0 },
  { type: 'TAXC', description: 'Transverse Axial Color', defaultTarget: 0 },
  { type: 'AXCL', description: 'Axial Color', defaultTarget: 0 },
  { type: 'LACL', description: 'Lateral Color', defaultTarget: 0 },
  { type: 'MTFT', description: 'MTF Tangential', defaultTarget: 0.5 },
  { type: 'MTFS', description: 'MTF Sagittal', defaultTarget: 0.5 },
  { type: 'BLEN', description: 'Back Focal Length', defaultTarget: 50 },
  { type: 'CTGT', description: 'Center Thickness >', defaultTarget: 2 },
  { type: 'CTLT', description: 'Center Thickness <', defaultTarget: 20 },
  { type: 'ETLX', description: 'Edge Thickness >', defaultTarget: 1 },
  { type: 'DIMD', description: 'Diameter', defaultTarget: 25 },
  { type: 'TTLT', description: 'Total Track Length', defaultTarget: 150 },
  { type: 'TTHI', description: 'Total Thickness', defaultTarget: 10 },
  { type: 'REAY', description: 'Real Ray Y height', defaultTarget: 0 },
  { type: 'REAX', description: 'Real Ray X height', defaultTarget: 0 },
  { type: 'OPLT', description: 'Operand Less Than', defaultTarget: 0 },
  { type: 'OPGT', description: 'Operand Greater Than', defaultTarget: 0 },
];

function createOperand(type: string, target: number, weight: number = 1): MeritOperand {
  return {
    id: nextOperandId++,
    type,
    target,
    weight,
    value: 0,
    contribution: 0,
    active: true,
    constraintMin: null,
    constraintMax: null,
  };
}

export function MeritFunctionEditor({ onMeritFunctionChange }: MeritFunctionEditorProps) {
  const [operands, setOperands] = useState<MeritOperand[]>([
    createOperand('EFFL', 100, 1),
    createOperand('WFNO', 2.8, 1),
    createOperand('SPHA', 0, 0.1),
    createOperand('COMA', 0, 0.1),
  ]);
  const [selectedOperand, setSelectedOperand] = useState<number | null>(null);

  const updateOperand = useCallback((id: number, updates: Partial<MeritOperand>) => {
    setOperands(prev => {
      const newOperands = prev.map(op => 
        op.id === id ? { ...op, ...updates } : op
      );
      onMeritFunctionChange?.(newOperands);
      return newOperands;
    });
  }, [onMeritFunctionChange]);

  const addOperand = useCallback((type: string) => {
    const catalog = OPERAND_CATALOG.find(o => o.type === type);
    if (!catalog) return;
    const newOperand = createOperand(type, catalog.defaultTarget, 1);
    setOperands(prev => {
      const newOperands = [...prev, newOperand];
      onMeritFunctionChange?.(newOperands);
      return newOperands;
    });
  }, [onMeritFunctionChange]);

  const removeOperand = useCallback((id: number) => {
    setOperands(prev => {
      const newOperands = prev.filter(op => op.id !== id);
      onMeritFunctionChange?.(newOperands);
      return newOperands;
    });
  }, [onMeritFunctionChange]);

  const moveOperand = useCallback((id: number, direction: 'up' | 'down') => {
    setOperands(prev => {
      const index = prev.findIndex(op => op.id === id);
      if (index < 0) return prev;
      const newIndex = direction === 'up' ? index - 1 : index + 1;
      if (newIndex < 0 || newIndex >= prev.length) return prev;
      const newOperands = [...prev];
      [newOperands[index], newOperands[newIndex]] = [newOperands[newIndex], newOperands[index]];
      onMeritFunctionChange?.(newOperands);
      return newOperands;
    });
  }, [onMeritFunctionChange]);

  const totalMerit = operands.reduce((sum, op) => {
    if (!op.active) return sum;
    return sum + op.weight * Math.pow(op.value - op.target, 2);
  }, 0);

  const formatValue = (value: number) => {
    if (Math.abs(value) < 0.001) return value.toExponential(3);
    if (Math.abs(value) > 1000) return value.toFixed(1);
    return value.toFixed(4);
  };

  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden bg-white">
      <div className="bg-gray-100 px-3 py-2 border-b border-gray-200">
        <div className="flex justify-between items-center">
          <h3 className="text-sm font-semibold text-gray-700">Merit Function Editor</h3>
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500">Total:</span>
            <span className={`text-sm font-mono ${totalMerit < 1 ? 'text-green-600' : 'text-orange-600'}`}>
              {formatValue(totalMerit)}
            </span>
          </div>
        </div>
      </div>
      
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              <th className="px-2 py-1 text-left text-gray-600 font-medium w-8">#</th>
              <th className="px-2 py-1 text-left text-gray-600 font-medium">Type</th>
              <th className="px-2 py-1 text-left text-gray-600 font-medium">Description</th>
              <th className="px-2 py-1 text-center text-gray-600 font-medium w-8">Act</th>
              <th className="px-2 py-1 text-right text-gray-600 font-medium">Target</th>
              <th className="px-2 py-1 text-right text-gray-600 font-medium">Weight</th>
              <th className="px-2 py-1 text-right text-gray-600 font-medium">Value</th>
              <th className="px-2 py-1 text-right text-gray-600 font-medium">Contrib</th>
              <th className="px-2 py-1 text-center text-gray-600 font-medium">Min</th>
              <th className="px-2 py-1 text-center text-gray-600 font-medium">Max</th>
              <th className="px-2 py-1 text-center text-gray-600 font-medium w-16">Move</th>
              <th className="px-2 py-1 text-center text-gray-600 font-medium w-8">Del</th>
            </tr>
          </thead>
          <tbody>
            {operands.map((operand, index) => {
              const catalog = OPERAND_CATALOG.find(o => o.type === operand.type);
              return (
                <tr
                  key={operand.id}
                  className={`border-b border-gray-100 hover:bg-blue-50 ${
                    !operand.active ? 'opacity-50' : ''
                  } ${selectedOperand === operand.id ? 'bg-blue-100' : ''}`}
                  onClick={() => setSelectedOperand(operand.id)}
                >
                  <td className="px-2 py-1 text-gray-500">{index + 1}</td>
                  <td className="px-2 py-1 font-mono font-medium text-gray-700">{operand.type}</td>
                  <td className="px-2 py-1 text-gray-600">{catalog?.description ?? ''}</td>
                  <td className="px-2 py-1 text-center">
                    <input
                      type="checkbox"
                      checked={operand.active}
                      onChange={(e) => updateOperand(operand.id, { active: e.target.checked })}
                      className="w-3 h-3"
                    />
                  </td>
                  <td className="px-2 py-1 text-right">
                    <input
                      type="number"
                      value={operand.target}
                      onChange={(e) => updateOperand(operand.id, { target: parseFloat(e.target.value) || 0 })}
                      className="w-20 px-1 py-0.5 text-right text-xs border border-gray-200 rounded"
                      step="any"
                    />
                  </td>
                  <td className="px-2 py-1 text-right">
                    <input
                      type="number"
                      value={operand.weight}
                      onChange={(e) => updateOperand(operand.id, { weight: parseFloat(e.target.value) || 0 })}
                      className="w-16 px-1 py-0.5 text-right text-xs border border-gray-200 rounded"
                      step="0.1"
                      min="0"
                    />
                  </td>
                  <td className="px-2 py-1 text-right font-mono text-gray-800">
                    {formatValue(operand.value)}
                  </td>
                  <td className="px-2 py-1 text-right font-mono text-gray-600">
                    {formatValue(operand.contribution)}
                  </td>
                  <td className="px-2 py-1 text-center">
                    <input
                      type="number"
                      value={operand.constraintMin ?? ''}
                      onChange={(e) => updateOperand(operand.id, { 
                        constraintMin: e.target.value ? parseFloat(e.target.value) : null 
                      })}
                      className="w-14 px-1 py-0.5 text-xs border border-gray-200 rounded"
                      placeholder="-"
                      step="any"
                    />
                  </td>
                  <td className="px-2 py-1 text-center">
                    <input
                      type="number"
                      value={operand.constraintMax ?? ''}
                      onChange={(e) => updateOperand(operand.id, { 
                        constraintMax: e.target.value ? parseFloat(e.target.value) : null 
                      })}
                      className="w-14 px-1 py-0.5 text-xs border border-gray-200 rounded"
                      placeholder="-"
                      step="any"
                    />
                  </td>
                  <td className="px-2 py-1 text-center">
                    <div className="flex justify-center gap-0.5">
                      <button
                        onClick={(e) => { e.stopPropagation(); moveOperand(operand.id, 'up'); }}
                        disabled={index === 0}
                        className="px-1 text-gray-400 hover:text-gray-700 disabled:opacity-30"
                      >
                        \u25B2
                      </button>
                      <button
                        onClick={(e) => { e.stopPropagation(); moveOperand(operand.id, 'down'); }}
                        disabled={index === operands.length - 1}
                        className="px-1 text-gray-400 hover:text-gray-700 disabled:opacity-30"
                      >
                        \u25BC
                      </button>
                    </div>
                  </td>
                  <td className="px-2 py-1 text-center">
                    <button
                      onClick={(e) => { e.stopPropagation(); removeOperand(operand.id); }}
                      className="text-red-400 hover:text-red-600 text-xs"
                    >
                      X
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      
      <div className="bg-gray-50 px-3 py-2 border-t border-gray-200">
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-600">Add operand:</span>
          <select
            onChange={(e) => {
              if (e.target.value) {
                addOperand(e.target.value);
                e.target.value = '';
              }
            }}
            className="text-xs border border-gray-200 rounded px-2 py-1"
            defaultValue=""
          >
            <option value="">Select...</option>
            {OPERAND_CATALOG.map(op => (
              <option key={op.type} value={op.type}>
                {op.type} - {op.description}
              </option>
            ))}
          </select>
        </div>
      </div>
      
      <div className="px-3 py-2 border-t border-gray-200">
        <div className="text-xs text-gray-600 mb-1">Residual Breakdown</div>
        <div className="flex gap-1 h-4">
          {operands.filter(op => op.active && op.contribution > 0).map(op => {
            const totalContrib = operands.reduce((s, o) => s + (o.active ? o.contribution : 0), 0);
            const pct = totalContrib > 0 ? (op.contribution / totalContrib) * 100 : 0;
            return (
              <div
                key={op.id}
                className="bg-blue-500 h-full"
                style={{ width: `${pct}%` }}
                title={`${op.type}: ${formatValue(op.contribution)} (${pct.toFixed(1)}%)`}
              />
            );
          })}
        </div>
      </div>
    </div>
  );
}
