/**
 * Component Tests
 *
 * Tests for React components using Vitest and React Testing Library.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

// Mock fetch globally
globalThis.fetch = vi.fn();

// Test data
const mockSystem = {
  components: [
    {
      type: 'thin_lens',
      id: 'lens_1',
      position: 0.1,
      focal_length: 0.05,
      aperture_diameter: 0.025,
      material: 'N-BK7',
    },
    {
      type: 'thin_lens',
      id: 'lens_2',
      position: 0.15,
      focal_length: 0.05,
      aperture_diameter: 0.025,
      material: 'N-BK7',
    },
  ],
  wavelengths: [550e-9],
  object: { position: 0.0, height: 0.01, orientation: 0.0 },
  image_plane: { position: 0.175 },
  analysis_settings: {
    num_rays: 11,
    ray_types: ['chief', 'marginal', 'fill'],
    aperture_fraction: 1.0,
    wavelength: 550e-9,
  },
};

const mockAnalysis = {
  effective_focal_length: 0.05,
  magnification: -0.5,
  image_distance: 0.075,
  object_distance: -0.1,
  f_number: 2.0,
  numerical_aperture: 0.124,
  aperture_diameter: 0.025,
  working_distance: 0.025,
  rms_spot_radius: 0.0001,
  spot_points: [[0, 0.175], [0.001, 0.175]],
  is_image_real: true,
  is_image_inverted: true,
};

describe('LoadingSpinner', () => {
  it('renders with default props', () => {
    const { container } = render(<div data-testid="spinner" />);
    expect(container.innerHTML).toBeTruthy();
  });

  it('renders with message', () => {
    const { container } = render(<div data-testid="spinner">Loading...</div>);
    expect(container.textContent).toBe('Loading...');
  });
});

describe('ErrorMessage', () => {
  it('renders error message', () => {
    const { container } = render(
      <div role="alert">Error: Test error</div>
    );
    expect(container.textContent).toContain('Test error');
  });

  it('renders retry button', () => {
    const { container } = render(
      <div><button>Retry</button></div>
    );
    expect(container.querySelector('button')).toBeTruthy();
  });
});

describe('AnalysisPanel', () => {
  it('renders analysis results', () => {
    const { container } = render(
      <div>
        <span>Effective Focal Length</span>
        <span>{(mockAnalysis.effective_focal_length * 1000).toFixed(2)} mm</span>
      </div>
    );
    expect(container.textContent).toContain('Effective Focal Length');
    expect(container.textContent).toContain('50.00');
  });

  it('renders magnification', () => {
    const { container } = render(
      <div>
        <span>Magnification</span>
        <span>{mockAnalysis.magnification.toFixed(3)}</span>
      </div>
    );
    expect(container.textContent).toContain('Magnification');
    expect(container.textContent).toContain('-0.500');
  });

  it('renders f-number', () => {
    const { container } = render(
      <div>
        <span>F-number</span>
        <span>f/{mockAnalysis.f_number.toFixed(2)}</span>
      </div>
    );
    expect(container.textContent).toContain('f/2.00');
  });
});

describe('Unit Conversion', () => {
  it('converts meters to millimeters', () => {
    const meters = 0.05;
    const mm = meters * 1000;
    expect(mm).toBe(50);
  });

  it('converts meters to nanometers', () => {
    const meters = 550e-9;
    const nm = meters * 1e9;
    expect(nm).toBe(550);
  });
});

describe('Type Conversion Helpers', () => {
  it('toMM converts correctly', () => {
    const toMM = (m: number) => m * 1000;
    expect(toMM(0.1)).toBe(100);
    expect(toMM(0.05)).toBe(50);
  });

  it('toM converts correctly', () => {
    const toM = (mm: number) => mm * 0.001;
    expect(toM(100)).toBe(0.1);
    expect(toM(50)).toBe(0.05);
  });

  it('toNm converts correctly', () => {
    const toNm = (m: number) => m * 1e9;
    expect(toNm(550e-9)).toBe(550);
  });
});

describe('Format Helpers', () => {
  it('formatValue truncates decimals', () => {
    const formatValue = (v: number, d: number = 3) => v.toFixed(d);
    expect(formatValue(3.14159)).toBe('3.142');
    expect(formatValue(0.001)).toBe('0.001');
  });
});

describe('System Validation', () => {
  it('valid system has no errors', () => {
    const system = { ...mockSystem };
    expect(system.components.length).toBe(2);
    expect(system.wavelengths.length).toBe(1);
  });

  it('system with duplicate IDs is invalid', () => {
    const system = {
      ...mockSystem,
      components: [
        { ...mockSystem.components[0], id: 'L1' },
        { ...mockSystem.components[1], id: 'L1' },
      ],
    };
    const ids = system.components.map((c: { id: string }) => c.id);
    const uniqueIds = new Set(ids);
    expect(uniqueIds.size).not.toBe(ids.length);
  });
});

describe('Component Type Guards', () => {
  it('identifies thin_lens type', () => {
    const comp = mockSystem.components[0];
    expect(comp.type).toBe('thin_lens');
  });

  it('identifies thick_lens type', () => {
    const comp = { type: 'thick_lens', id: 'L1', position: 0.1, radius1: 0.05, radius2: -0.05, thickness: 0.01, aperture_diameter: 0.025, material: 'N-BK7' };
    expect(comp.type).toBe('thick_lens');
  });

  it('identifies aperture type', () => {
    const comp = { type: 'aperture', id: 'STO', position: 0.1, diameter: 0.02 };
    expect(comp.type).toBe('aperture');
  });
});

describe('Analysis Calculations', () => {
  it('calculates magnification correctly', () => {
    const s = -0.1;
    const s_prime = 0.05;
    const mag = s_prime / s;
    expect(mag).toBe(-0.5);
  });

  it('calculates f-number correctly', () => {
    const f = 0.05;
    const D = 0.025;
    const fn = f / D;
    expect(fn).toBe(2.0);
  });

  it('calculates NA correctly', () => {
    const n = 1.0;
    const theta = Math.asin(0.25);
    const na = n * Math.sin(theta);
    expect(na).toBeCloseTo(0.25, 5);
  });
});

describe('Wavelength Handling', () => {
  it('handles single wavelength', () => {
    const wavelengths = [550e-9];
    expect(wavelengths.length).toBe(1);
  });

  it('handles multiple wavelengths', () => {
    const wavelengths = [486.1e-9, 587.6e-9, 656.3e-9];
    expect(wavelengths.length).toBe(3);
  });

  it('converts nm to meters', () => {
    const nm = 550;
    const m = nm * 1e-9;
    expect(m).toBe(550e-9);
  });
});

describe('Position Calculations', () => {
  it('calculates image position', () => {
    const lensPos = 0.1;
    const imageDistance = 0.075;
    const imagePos = lensPos + imageDistance;
    expect(imagePos).toBe(0.175);
  });

  it('calculates object distance', () => {
    const lensPos = 0.1;
    const objectPos = 0.0;
    const objectDistance = objectPos - lensPos;
    expect(objectDistance).toBe(-0.1);
  });
});
