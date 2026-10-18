/**
 * Help Tooltip Component.
 *
 * Shows helpful information about optical parameters on hover.
 */

import { useState } from 'react';

interface HelpTooltipProps {
  content: string;
  position?: 'top' | 'bottom' | 'left' | 'right';
}

export function HelpTooltip({ content, position = 'top' }: HelpTooltipProps) {
  const [visible, setVisible] = useState(false);

  const positionClasses = {
    top: 'bottom-full left-1/2 -translate-x-1/2 mb-2',
    bottom: 'top-full left-1/2 -translate-x-1/2 mt-2',
    left: 'right-full top-1/2 -translate-y-1/2 mr-2',
    right: 'left-full top-1/2 -translate-y-1/2 ml-2',
  };

  return (
    <span
      className="relative inline-block ml-1"
      onMouseEnter={() => setVisible(true)}
      onMouseLeave={() => setVisible(false)}
    >
      <span className="inline-flex items-center justify-center w-4 h-4 text-xs text-gray-500 bg-gray-200 rounded-full cursor-help">
        ?
      </span>
      {visible && (
        <span
          className={`absolute z-50 px-2 py-1 text-xs text-white bg-gray-800 rounded whitespace-nowrap ${positionClasses[position]}`}
        >
          {content}
        </span>
      )}
    </span>
  );
}

export const opticalParameterHelp: Record<string, string> = {
  focal_length: 'Focal length (f): Distance from lens where parallel rays converge. Positive for converging, negative for diverging.',
  aperture_diameter: 'Aperture diameter (D): Size of the lens opening. Determines light gathering ability and depth of field.',
  f_number: 'F-number (f/#): Ratio of focal length to aperture diameter. Lower values = brighter image, shallower depth of field.',
  numerical_aperture: 'Numerical aperture (NA): n*sin(θ). Measures light gathering ability. Higher NA = better resolution.',
  magnification: 'Magnification (m): Image height / Object height. Negative means inverted image.',
  wavelength: 'Wavelength of light in meters. Visible spectrum: 380-700nm. Default 550nm (green).',
  object_distance: 'Distance from object to first lens. Negative in optics convention (object to the left).',
  image_distance: 'Distance from last lens to image plane. Positive for real images, negative for virtual.',
  radius: 'Radius of curvature. Positive if center of curvature is to the right (convex toward incoming light).',
  thickness: 'Center thickness of a thick lens. Affects principal plane positions.',
  rms_spot: 'RMS spot radius: Root-mean-square size of the geometric spot diagram. Smaller = better image quality.',
  material: 'Optical glass material. Affects refractive index and dispersion (chromatic aberration).',
  sellmeier: 'Sellmeier equation describes how refractive index varies with wavelength.',
  dispersion: 'Dispersion: Variation of refractive index with wavelength. Causes chromatic aberration.',
  spherical_aberration: 'Spherical aberration: Rays at different heights focus at different points.',
  coma: 'Coma: Off-axis points appear comet-shaped. Proportional to field angle and aperture squared.',
  astigmatism: 'Astigmatism: Tangential and sagittal foci are at different positions.',
  field_curvature: 'Field curvature: Image plane is curved, not flat. Also called Petzval curvature.',
  distortion: 'Deviation from ideal image geometry. Barrel or pincushion shape.',
};
