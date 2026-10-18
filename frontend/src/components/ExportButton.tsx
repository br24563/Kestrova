/**
 * Export Button Component.
 *
 * Provides export functionality for SVG elements and data.
 */

interface ExportButtonProps {
  svgId?: string;
  filename?: string;
  data?: object;
  type?: 'svg' | 'json' | 'csv';
}

export function ExportButton({ svgId, filename = 'export', data, type = 'svg' }: ExportButtonProps) {
  const handleExport = () => {
    if (type === 'svg' && svgId) {
      exportSvg(svgId, filename);
    } else if (type === 'json' && data) {
      exportJson(data, filename);
    } else if (type === 'csv' && data) {
      exportCsv(data, filename);
    }
  };

  return (
    <button
      onClick={handleExport}
      className="px-2 py-1 text-xs bg-gray-100 hover:bg-gray-200 rounded border border-gray-300 transition-colors"
      title={`Export as ${type.toUpperCase()}`}
    >
      Export {type.toUpperCase()}
    </button>
  );
}

function exportSvg(svgId: string, filename: string) {
  const svgElement = document.getElementById(svgId);
  if (!svgElement) {
    console.error(`SVG element with id '${svgId}' not found`);
    return;
  }

  const serializer = new XMLSerializer();
  const svgString = serializer.serializeToString(svgElement);
  const blob = new Blob([svgString], { type: 'image/svg+xml' });
  downloadBlob(blob, `${filename}.svg`);
}

function exportJson(data: object, filename: string) {
  const jsonString = JSON.stringify(data, null, 2);
  const blob = new Blob([jsonString], { type: 'application/json' });
  downloadBlob(blob, `${filename}.json`);
}

function exportCsv(data: object, filename: string) {
  // Simple CSV export for array data
  const rows = Array.isArray(data) ? data : [data];
  if (rows.length === 0) return;

  const headers = Object.keys(rows[0]);
  const csvLines = [
    headers.join(','),
    ...rows.map(row => headers.map(h => JSON.stringify((row as Record<string, unknown>)[h] ?? '')).join(','))
  ];
  const blob = new Blob([csvLines.join('\n')], { type: 'text/csv' });
  downloadBlob(blob, `${filename}.csv`);
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
