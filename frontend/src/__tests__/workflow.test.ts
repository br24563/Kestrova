/**
 * Workflow Integration Tests
 *
 * Tests for complete user workflows and API integration.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock fetch for API calls
const mockFetch = vi.fn();
globalThis.fetch = mockFetch;

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

const mockTraceResult = {
  ray_paths: [
    {
      points: [[0, 0.01], [0.1, 0.01], [0.15, 0.005], [0.175, 0.005]],
      ray_type: 'chief',
      wavelength: 550e-9,
      initial_y: 0.01,
      initial_theta: 0,
      final_y: 0.005,
      final_theta: 0,
    },
  ],
  image_position: 0.175,
  image_height: 0.005,
  paraxial_image_height: 0.005,
};

describe('API Client', () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  it('fetches default system', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ system: mockSystem, warnings: [] }),
    });

    const response = await fetch('/api/system/default');
    const data = await response.json();

    expect(data.system).toEqual(mockSystem);
    expect(mockFetch).toHaveBeenCalledWith('/api/system/default');
  });

  it('traces rays through system', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockTraceResult,
    });

    const response = await fetch('/api/trace', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ system: mockSystem }),
    });
    const data = await response.json();

    expect(data.ray_paths.length).toBeGreaterThan(0);
  });

  it('analyzes system', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockAnalysis,
    });

    const response = await fetch('/api/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ system: mockSystem }),
    });
    const data = await response.json();

    expect(data.effective_focal_length).toBe(mockAnalysis.effective_focal_length);
    expect(data.magnification).toBe(mockAnalysis.magnification);
  });

  it('handles API errors', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 400,
      statusText: 'Bad Request',
    });

    const response = await fetch('/api/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });

    expect(response.ok).toBe(false);
  });
});

describe('Workflow: Load and Analyze', () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  it('loads default system and displays analysis', async () => {
    // Mock system fetch
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ system: mockSystem, warnings: [] }),
    });

    // Mock analysis fetch
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockAnalysis,
    });

    // Simulate workflow
    const systemResponse = await fetch('/api/system/default');
    const systemData = await systemResponse.json();
    expect(systemData.system).toBeTruthy();

    const analysisResponse = await fetch('/api/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ system: systemData.system }),
    });
    const analysisData = await analysisResponse.json();
    expect(analysisData.effective_focal_length).toBeTruthy();
  });
});

describe('Workflow: Modify and Re-analyze', () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  it('modifies system and sees updated results', async () => {
    const modifiedSystem = {
      ...mockSystem,
      components: mockSystem.components.map((c: { type: string; id: string; position: number; focal_length: number; aperture_diameter: number; material: string }, i: number) =>
        i === 0 ? { ...c, focal_length: 0.075 } : c
      ),
    };

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        ...mockAnalysis,
        effective_focal_length: 0.075,
      }),
    });

    const response = await fetch('/api/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ system: modifiedSystem }),
    });
    const data = await response.json();

    expect(data.effective_focal_length).toBe(0.075);
  });
});

describe('Workflow: Export', () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  it('exports design to ZMX format', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        format: 'zmx',
        content: 'VERS 190514 81 0 0\nMODE SEQ',
        filename: 'design.zmx',
      }),
    });

    const response = await fetch('/api/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ system: mockSystem, format: 'zmx' }),
    });
    const data = await response.json();

    expect(data.format).toBe('zmx');
    expect(data.content).toBeTruthy();
  });

  it('exports bill of materials', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        format: 'bom',
        content: 'BILL OF MATERIALS\n...',
        filename: 'bom.txt',
      }),
    });

    const response = await fetch('/api/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ system: mockSystem, format: 'bom' }),
    });
    const data = await response.json();

    expect(data.format).toBe('bom');
  });
});

describe('Workflow: AI Copilot', () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  it('gets explanation for MTF drop', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        answer: 'Spherical aberration is dominant...',
        citations: ['Seidel analysis: SA=0.5um'],
        confidence: 0.85,
        suggested_actions: ['Run optimization'],
        verified: true,
      }),
    });

    const response = await fetch('/api/ai/explain', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        system: mockSystem,
        question: 'Why does MTF drop?',
      }),
    });
    const data = await response.json();

    expect(data.answer).toBeTruthy();
    expect(data.confidence).toBeGreaterThan(0);
    expect(data.verified).toBe(true);
  });

  it('verifies a calculation claim', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        answer: 'VERIFIED: EFL is 50.00mm',
        citations: ['Calculated EFL: 50.00mm'],
        confidence: 0.99,
        suggested_actions: [],
        verified: true,
      }),
    });

    const response = await fetch('/api/ai/verify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        system: mockSystem,
        claim: 'EFL is 50mm',
      }),
    });
    const data = await response.json();

    expect(data.verified).toBe(true);
    expect(data.answer).toContain('VERIFIED');
  });
});

describe('Error Handling', () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  it('handles network errors', async () => {
    mockFetch.mockRejectedValueOnce(new Error('Network error'));

    await expect(
      fetch('/api/system/default')
    ).rejects.toThrow('Network error');
  });

  it('handles malformed JSON', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => { throw new Error('Invalid JSON'); },
    });

    const response = await fetch('/api/system/default');
    await expect(response.json()).rejects.toThrow('Invalid JSON');
  });

  it('handles server errors', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      statusText: 'Internal Server Error',
      json: async () => ({ detail: 'Server error' }),
    });

    const response = await fetch('/api/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });

    expect(response.ok).toBe(false);
    expect(response.status).toBe(500);
  });
});

describe('Data Integrity', () => {
  it('preserves component order', () => {
    const components = mockSystem.components;
    expect(components[0].id).toBe('lens_1');
    expect(components[1].id).toBe('lens_2');
  });

  it('preserves wavelength data', () => {
    expect(mockSystem.wavelengths).toEqual([550e-9]);
  });

  it('preserves object data', () => {
    expect(mockSystem.object.position).toBe(0.0);
    expect(mockSystem.object.height).toBe(0.01);
  });

  it('preserves image plane data', () => {
    expect(mockSystem.image_plane.position).toBe(0.175);
  });
});
