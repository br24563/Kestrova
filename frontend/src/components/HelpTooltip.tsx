/**
 * Help Tooltip Component.
 *
 * Shows helpful information about optical parameters on hover or focus.
 */

import { useState } from 'react';

interface HelpTooltipProps {
  content: string;
  position?: 'top' | 'bottom' | 'left' | 'right' | 'bottom-start' | 'bottom-end';
}

export function HelpTooltip({ content, position = 'bottom-start' }: HelpTooltipProps) {
  const [visible, setVisible] = useState(false);

  const positionClasses = {
    top: 'bottom-full left-1/2 -translate-x-1/2 mb-2',
    bottom: 'top-full left-1/2 -translate-x-1/2 mt-2',
    left: 'right-full top-1/2 -translate-y-1/2 mr-2',
    right: 'left-full top-1/2 -translate-y-1/2 ml-2',
    'bottom-start': 'top-full left-0 mt-2',
    'bottom-end': 'top-full right-0 mt-2',
  };

  return (
    <span
      className="relative inline-block ml-1 normal-case"
      onMouseEnter={() => setVisible(true)}
      onMouseLeave={() => setVisible(false)}
      onFocus={() => setVisible(true)}
      onBlur={() => setVisible(false)}
    >
      <span
        tabIndex={0}
        aria-label={content}
        className="inline-flex items-center justify-center w-4 h-4 text-xs text-gray-500 bg-gray-200 rounded-full cursor-help"
      >
        ?
      </span>
      {visible && (
        <span
          role="tooltip"
          className={`absolute z-50 w-56 px-2 py-1 text-xs font-normal text-white bg-gray-800 rounded shadow whitespace-normal ${positionClasses[position]}`}
        >
          {content}
        </span>
      )}
    </span>
  );
}

/** Definitions as computed by the backend (optics/analysis.py, optics/seidel.py). */
export const opticalParameterHelp: Record<string, string> = {
  effective_focal_length: 'Effective focal length: distance from the rear principal plane to the rear focal point (paraxial). Shown as ∞ for an afocal system.',
  focal_length: 'Focal length (f): distance from the lens at which parallel rays converge. Positive for converging, negative for diverging.',
  aperture_diameter: 'Clear aperture diameter (D) of the limiting stop. Sets light gathering and, with the focal length, the F-number.',
  f_number: 'F-number: effective focal length divided by the entrance-pupil diameter (the infinite-conjugate F/#).',
  numerical_aperture: "Image-space numerical aperture n' sin U' of the real marginal ray. Higher NA means finer diffraction-limited resolution.",
  magnification: 'Paraxial transverse magnification: image height / object height. Negative means inverted; 0 for an object at infinity.',
  wavelength: 'Analysis wavelength. Visible light spans roughly 380–750 nm; the default is 550 nm (green).',
  object_distance: 'Object position minus the first surface position: negative when the object is before the first surface.',
  image_distance: 'Distance from the last surface to the paraxial image, along the direction light travels after it.',
  working_distance: 'Distance from the last surface to the current image plane, along the direction of travel.',
  radius: 'Radius of curvature. Positive when the centre of curvature lies after the surface (to the right).',
  thickness: 'Centre thickness of a thick lens along the axis.',
  rms_spot: 'RMS radius of the real-ray spot at the image plane for the full-field point (geometric, no diffraction).',
  material: 'Optical glass. Its dispersion formula sets the refractive index at each wavelength.',
  dispersion: 'Variation of refractive index with wavelength; causes chromatic aberration.',
  chromatic: 'Axial colour: image position at the F line minus the C line. Lateral colour: chief-ray height difference in the d-line image plane.',
  spherical_aberration: 'Spherical aberration: rays through different pupil heights focus at different points along the axis.',
  coma: 'Coma: off-axis points image as comet-shaped blurs; grows with field and with aperture squared.',
  astigmatism: 'Astigmatism: tangential and sagittal fans focus at different distances.',
  field_curvature: 'Field curvature: best focus lies on a curved surface rather than the flat image plane.',
  distortion: 'Distortion: real chief-ray height relative to the paraxial height. Positive = pincushion, negative = barrel.',
};
