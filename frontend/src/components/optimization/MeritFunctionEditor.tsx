/**
 * Merit Function Editor Component.
 *
 * Edits the constraint operands passed to the hybrid optimizer. Each
 * operand bounds one quantity between Min and Max; the optimizer adds
 * weight x violation x 1e6 to the merit for any operand outside its bounds.
 * Current values and penalties come from the backend's own evaluator.
 */

import type { OpticalSystem, LengthUnit } from '../../types';
import { fromMeters, toMeters, LENGTH_UNIT_LABELS } from '../../types';
import { evaluateConstraints, type ConstraintSpec } from '../../api';
import { useAnalysis } from '../analysis/useAnalysis';

export interface MeritOperand {
  id: number;
  type: string;
  componentIndex: number | null;
  min: number | null;   // display units
  max: number | null;
  weight: number;
  active: boolean;
}

type Kind = 'length' | 'percent' | 'number';

/** Operand types supported by optics.advanced_optimization._get_constraint_value. */
export const OPERAND_CATALOG: { type: string; description: string; kind: Kind; perComponent?: boolean }[] = [
  { type: 'efl', description: 'Effective focal length', kind: 'length' },
  { type: 'bfl', description: 'Back focal length', kind: 'length' },
  { type: 'image_distance', description: 'Image distance', kind: 'length' },
  { type: 'magnification', description: 'Magnification', kind: 'number' },
  { type: 'f_number', description: 'F-number', kind: 'number' },
  { type: 'numerical_aperture', description: 'Numerical aperture', kind: 'number' },
  { type: 'rms_spot', description: 'RMS spot radius', kind: 'length' },
  { type: 'distortion', description: 'Distortion at full field (real)', kind: 'percent' },
  { type: 'total_track', description: 'First lens to image', kind: 'length' },
  { type: 'center_thickness', description: 'Centre thickness (thick lens)', kind: 'length', perComponent: true },
  { type: 'edge_thickness', description: 'Edge thickness (thick lens)', kind: 'length', perComponent: true },
  { type: 'air_gap', description: 'Air gap after component', kind: 'length', perComponent: true },
];

const kindOf = (type: string): Kind => OPERAND_CATALOG.find((o) => o.type === type)?.kind ?? 'number';

/** Display-unit value to the SI value the backend uses. */
function toSI(v: number, kind: Kind, unit: LengthUnit): number {
  return kind === 'length' ? toMeters(v, unit) : kind === 'percent' ? v / 100 : v;
}

function fromSI(v: number, kind: Kind, unit: LengthUnit): number {
  return kind === 'length' ? fromMeters(v, unit) : kind === 'percent' ? v * 100 : v;
}

/** Operands as the backend's constraint dicts (inactive ones dropped). */
export function operandsToConstraints(operands: MeritOperand[], unit: LengthUnit): ConstraintSpec[] {
  return operands.filter((o) => o.active).map((o) => {
    const k = kindOf(o.type);
    return {
      type: o.type,
      surface_index: o.componentIndex,
      lower: o.min === null ? null : toSI(o.min, k, unit),
      upper: o.max === null ? null : toSI(o.max, k, unit),
      weight: o.weight,
    };
  });
}

let nextOperandId = 1;

interface MeritFunctionEditorProps {
  system: OpticalSystem;
  displayUnit: LengthUnit;
  operands: MeritOperand[];
  onChange: (operands: MeritOperand[]) => void;
}

export function MeritFunctionEditor({ system, displayUnit, operands, onChange }: MeritFunctionEditorProps) {
  const unitLabel = LENGTH_UNIT_LABELS[displayUnit];
  const active = operands.filter((o) => o.active);
  const { data, error } = useAnalysis(
    () => active.length
      ? evaluateConstraints(system, operandsToConstraints(operands, displayUnit))
      : Promise.resolve({ constraints: [] }),
    [system, operands, displayUnit],
  );

  const update = (id: number, changes: Partial<MeritOperand>) =>
    onChange(operands.map((o) => (o.id === id ? { ...o, ...changes } : o)));

  const add = (type: string) => {
    const entry = OPERAND_CATALOG.find((o) => o.type === type);
    if (!entry) return;
    onChange([...operands, {
      id: nextOperandId++, type, componentIndex: entry.perComponent ? 0 : null,
      min: null, max: null, weight: 1, active: true,
    }]);
  };

  const parse = (s: string) => (s.trim() === '' || Number.isNaN(parseFloat(s)) ? null : parseFloat(s));
  const unitFor = (k: Kind) => (k === 'length' ? unitLabel : k === 'percent' ? '%' : '');
  const totalPenalty = data?.constraints.reduce((s, c) => s + (c.penalty ?? 0), 0) ?? 0;

  // results are returned for active operands only, in order
  let activeIndex = -1;

  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden bg-white">
      <div className="bg-gray-100 px-3 py-2 border-b border-gray-200 flex justify-between items-center">
        <h3 className="text-sm font-semibold text-gray-700">Constraint Operands</h3>
        <span className="text-xs text-gray-600">
          Penalty: <span className={`font-mono ${totalPenalty > 0 ? 'text-orange-600' : 'text-green-600'}`}>
            {totalPenalty.toPrecision(3)}
          </span>
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="bg-gray-50 border-b border-gray-200 text-gray-600">
            <tr>
              <th className="px-2 py-1 text-center">On</th>
              <th className="px-2 py-1 text-left">Operand</th>
              <th className="px-2 py-1 text-left">Component</th>
              <th className="px-2 py-1 text-right">Min</th>
              <th className="px-2 py-1 text-right">Max</th>
              <th className="px-2 py-1 text-right">Weight</th>
              <th className="px-2 py-1 text-right">Value</th>
              <th className="px-2 py-1 text-right">Penalty</th>
              <th className="px-2 py-1 text-center">Del</th>
            </tr>
          </thead>
          <tbody>
            {operands.map((op) => {
              const entry = OPERAND_CATALOG.find((o) => o.type === op.type);
              const k = kindOf(op.type);
              const res = op.active ? data?.constraints[++activeIndex] : undefined;
              return (
                <tr key={op.id} className={`border-b border-gray-100 ${op.active ? '' : 'opacity-50'}`}>
                  <td className="px-2 py-1 text-center">
                    <input type="checkbox" checked={op.active} className="w-3 h-3"
                      onChange={(e) => update(op.id, { active: e.target.checked })} />
                  </td>
                  <td className="px-2 py-1 text-gray-700">{entry?.description ?? op.type}</td>
                  <td className="px-2 py-1">
                    {entry?.perComponent ? (
                      <select
                        value={op.componentIndex ?? 0}
                        onChange={(e) => update(op.id, { componentIndex: parseInt(e.target.value) })}
                        className="text-xs border border-gray-200 rounded px-1 py-0.5"
                      >
                        {system.components.map((c, i) => <option key={c.id} value={i}>{c.id}</option>)}
                      </select>
                    ) : <span className="text-gray-400">system</span>}
                  </td>
                  {(['min', 'max'] as const).map((field) => (
                    <td key={field} className="px-2 py-1 text-right">
                      <input
                        type="number" step="any" placeholder="-"
                        value={op[field] ?? ''}
                        onChange={(e) => update(op.id, { [field]: parse(e.target.value) })}
                        className="w-20 px-1 py-0.5 text-right text-xs border border-gray-200 rounded"
                      />
                    </td>
                  ))}
                  <td className="px-2 py-1 text-right">
                    <input
                      type="number" step="0.1" min="0" value={op.weight}
                      onChange={(e) => update(op.id, { weight: parse(e.target.value) ?? 0 })}
                      className="w-14 px-1 py-0.5 text-right text-xs border border-gray-200 rounded"
                    />
                  </td>
                  <td className="px-2 py-1 text-right font-mono text-gray-800" title={res?.error ?? undefined}>
                    {res === undefined ? '' : res.value === null
                      ? <span className="text-red-500">{res.error ? 'n/a' : '∞'}</span>
                      : `${fromSI(res.value, k, displayUnit).toPrecision(5)} ${unitFor(k)}`}
                  </td>
                  <td className={`px-2 py-1 text-right font-mono ${res?.penalty ? 'text-orange-600' : 'text-gray-500'}`}>
                    {res?.penalty === undefined || res.penalty === null ? '' : res.penalty.toPrecision(3)}
                  </td>
                  <td className="px-2 py-1 text-center">
                    <button onClick={() => onChange(operands.filter((o) => o.id !== op.id))}
                      className="text-red-400 hover:text-red-600">X</button>
                  </td>
                </tr>
              );
            })}
            {operands.length === 0 && (
              <tr><td colSpan={9} className="px-2 py-2 text-gray-500">No operands: the optimizer uses the objective alone.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="bg-gray-50 px-3 py-2 border-t border-gray-200 flex items-center gap-2 text-xs">
        <span className="text-gray-600">Add operand:</span>
        <select
          value=""
          onChange={(e) => add(e.target.value)}
          className="text-xs border border-gray-200 rounded px-2 py-1"
        >
          <option value="">Select...</option>
          {OPERAND_CATALOG.map((o) => <option key={o.type} value={o.type}>{o.description}</option>)}
        </select>
        {error && <span className="text-red-500">{error}</span>}
      </div>
    </div>
  );
}
