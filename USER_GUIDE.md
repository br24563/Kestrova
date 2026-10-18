# User Guide

## Overview

AI Optical Design Engineer is a free, professional-grade optical design application for designing, simulating, and analyzing optical systems.

## Features

- **Optical System Designer**: Create and edit optical systems with an intuitive interface
- **Ray Tracing**: Sequential ray tracing through optical systems
- **Aberration Analysis**: Seidel aberrations, chromatic aberration, diffraction
- **Optimization**: Hybrid global+local optimization with constraints
- **Tolerance Analysis**: Monte Carlo tolerance analysis with sensitivity ranking
- **Stray Light Analysis**: Ghost reflections, PST, scatter paths
- **Import/Export**: Zemax, Code V, SVG drawings, BOM
- **AI Copilot**: Natural language interface with explainability

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- npm

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/USERNAME/ai-optical-design-engineer.git
   cd ai-optical-design-engineer
   ```

2. **Set up the backend:**
   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   # or: venv\Scripts\activate  # Windows
   pip install -r requirements.txt
   ```

3. **Set up the frontend:**
   ```bash
   cd frontend
   npm install
   ```

### Running the Application

1. **Start the backend:**
   ```bash
   cd backend
   source venv/bin/activate
   uvicorn api.main:app --reload --port 8000
   ```

2. **Start the frontend:**
   ```bash
   cd frontend
   npm run dev
   ```

3. **Open in browser:**
   Navigate to `http://localhost:5173`

## Interface

### Main Window

The interface is divided into three panels:

1. **Left Panel**: Component editor and project management
2. **Center**: Optical bench visualization
3. **Right Panel**: Analysis results and tools

### Header Controls

- **Preset**: Load preset optical systems
- **Units**: Switch between nm, μm, mm, cm, m
- **Save/Load**: Save and load projects
- **Undo/Redo**: History navigation
- **Dark/Light**: Theme toggle

### Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| Ctrl+S | Save project |
| Ctrl+L | Load project |
| Ctrl+D | Toggle dark mode |
| Ctrl+R | Refresh simulation |
| Ctrl+Z | Undo |
| Ctrl+Shift+Z | Redo |
| Ctrl+Y | Redo (alternative) |
| Escape | Clear error |

## Workflows

### 1. Design a System

1. Select a preset from the dropdown or start from scratch
2. Edit surface parameters in the prescription editor
3. See real-time updates in the optical bench

### 2. Analyze Performance

1. View spot diagram for geometric aberrations
2. Check ray fan for transverse aberrations
3. Examine OPD/wavefront for wavefront error
4. Review field curvature and distortion plots
5. Analyze chromatic aberration (LCA/TCA)

### 3. Optimize

1. Select parameters to optimize
2. Choose objective (RMS spot, EFL, magnification)
3. Set constraints (thickness, air gaps, etc.)
4. Run hybrid optimization
5. Review results

### 4. Tolerance Analysis

1. Define tolerance parameters
2. Run Monte Carlo analysis
3. Review sensitivity ranking
4. Check yield statistics
5. Apply compensators

### 5. Export

1. Choose export format:
   - ZMX (Zemax)
   - SEQ (Code V)
   - SVG (2D drawing)
   - BOM (Bill of Materials)
   - SAG (Sag table)
   - ISO 10110 (Optical drawing)
2. Download the file

## Preset Systems

| Preset | Description |
|--------|-------------|
| Single Lens | Single 100mm focal length lens |
| Keplerian Telescope | Two positive lenses (200mm + 100mm) |
| Galilean Telescope | Positive objective + negative eyepiece |
| Simple Microscope | Short FL objective + longer eyepiece |
| Beam Expander | Expands collimated beam |
| 4f Relay Lens | Two identical lenses at 2f spacing |
| Beam Collimator | Single lens collimating point source |
| Double-Gauss | Simplified 6-element camera lens |
| Thick Lens | Single thick biconvex lens |
| Parabolic Mirror | Newtonian telescope primary |

## Optical Conventions

### Sign Convention

- Light travels left to right (z-axis)
- Heights above axis are positive (y-axis)
- Object distance (s): NEGATIVE if object is to the LEFT
- Image distance (s'): POSITIVE if image is to the RIGHT
- Focal length: positive for converging, negative for diverging
- Radius: positive if center of curvature is to the RIGHT

### Units

All internal calculations use SI units (meters, radians). The UI displays values in the selected unit.

## Analysis Types

### Geometric Analysis

- **Spot Diagram**: Shows where rays intersect the image plane
- **Ray Fan**: Transverse aberration vs. pupil coordinate
- **Field Curvature**: Tangential/sagittal focus vs. field angle
- **Distortion**: Image distortion vs. field angle

### Wavefront Analysis

- **OPD**: Optical path difference vs. pupil coordinate
- **Wavefront**: Wavefront error map
- **PSF**: Point spread function
- **MTF**: Modulation transfer function

### Diffraction Analysis

- **Strehl ratio**: diffraction limited when Strehl >= 0.8 (Maréchal)
- **Airy Disk**: first dark ring radius 0.61 lambda / NA
- **Encircled Energy**: Energy fraction vs. radius
- **MTF vs Frequency**: FFT MTF from the real wavefront, with the
  diffraction limit for the same NA

Thin lenses are ideal (aberration-free) lenses; use thick lenses, surfaces
and mirrors to see real aberrations.

### Chromatic Analysis

- **LCA**: Longitudinal chromatic aberration
- **TCA**: Transverse chromatic aberration

## Optimization

### Objectives

- **RMS Spot**: Minimize RMS spot radius
- **EFL**: Target effective focal length
- **Magnification**: Target magnification

### Algorithms

- **Global**: Differential Evolution, Particle Swarm
- **Local**: Damped Least Squares, L-BFGS-B
- **Hybrid**: Global search followed by local refinement

### Constraints

- Center thickness (min/max)
- Edge thickness (min)
- Air gap (min)
- Total track length (max)
- Back focal length (target)
- Distortion (max)

## Tolerance Analysis

### Error Sources

- Radius error (power fringes at 546.1 nm over the clear aperture)
- Center thickness error
- Air-space error
- Element decenter
- Element tilt

Index, Abbe, irregularity and wedge errors are not modelled yet.

### Compensators

Any system parameter can be a compensator (typically the image plane
position or an air space); it is re-optimized within its range after each
Monte Carlo trial.

### Yield Analysis

- **Yield**: Percentage within specification
- **Cpk**: Process capability index
- **Sensitivity**: Parameter contribution to variation

## AI Copilot

### Features

- **Explain**: Explain why MTF drops or aberrations occur
- **Suggest**: Get design family recommendations
- **Verify**: Verify claims about the system
- **NL to Prescription**: Convert natural language to prescription

### Example Queries

- "Why does MTF drop at the field edge?"
- "What are the dominant aberrations?"
- "Suggest a design for 5x magnification at f/2.8"
- "Verify that EFL is 100mm"

## Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| System won't load | Check backend is running on port 8000 |
| Analysis fails | Check system has valid components |
| Optimization doesn't converge | Try different initial parameters |
| Export fails | Check file permissions |

### Getting Help

1. Check the documentation
2. Run tests: `pytest tests/ -v`
3. Check GitHub Issues
4. Submit a bug report

## Scientific References

- Born & Wolf, "Principles of Optics", 7th Edition
- Smith, "Modern Optical Engineering", 4th Edition
- Hecht, "Optics", 5th Edition
- Schott Glass Catalog, 2024
- ISO 10110: Optics and photonics - Indications in drawings

## License

This project is for educational and research purposes.
