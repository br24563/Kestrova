/**
 * Design report of the prescription (system data, first order,
 * prescription, field performance, MTF, Seidel, tolerance budget, ISO
 * 10110 drawings) previewed in the app and saved as PDF or HTML. The
 * desktop app writes the PDF itself; in a browser the print dialog does.
 */
import { useRef, useState } from "react";
import type { LensData } from "../../types";
import { lensReport } from "../../api";

interface DesktopApi {
  savePdf?: (html: string, name: string) => Promise<string | null>;
}

function desktop(): DesktopApi | undefined {
  return (window as unknown as { electronAPI?: DesktopApi }).electronAPI;
}

export function fileName(title: string): string {
  const base = title.replace(/[^\w.-]+/g, "_").replace(/^_+|_+$/g, "");
  return base || "lens_report";
}

export function DesignReportPanel({ lens }: { lens: LensData | null }) {
  const [title, setTitle] = useState("");
  const [author, setAuthor] = useState("");
  const [mtf, setMtf] = useState(true);
  const [tolerances, setTolerances] = useState(true);
  const [drawings, setDrawings] = useState(true);
  const [html, setHtml] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const frame = useRef<HTMLIFrameElement>(null);

  if (!lens)
    return (
      <p className="p-4 text-xs text-gray-500">
        The design report works on the lens data (open or convert a lens in the
        Lens Data Editor).
      </p>
    );

  const name = fileName(title || lens.name);

  const generate = async () => {
    setRunning(true);
    setError(null);
    setMessage(null);
    try {
      const out = await lensReport(lens, {
        title: title || null,
        author,
        mtf,
        tolerances,
        drawings,
      });
      setHtml(out.html);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Report failed");
    } finally {
      setRunning(false);
    }
  };

  const savePdf = async () => {
    if (!html) return;
    const api = desktop();
    if (api?.savePdf) {
      try {
        const path = await api.savePdf(html, `${name}.pdf`);
        if (path) setMessage(`Saved ${path}`);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Saving failed");
      }
    } else {
      frame.current?.contentWindow?.print();
    }
  };

  const saveHtml = () => {
    if (!html) return;
    const url = URL.createObjectURL(new Blob([html], { type: "text/html" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `${name}.html`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="p-4 space-y-3 text-xs" data-testid="design-report">
      <div className="flex flex-wrap items-center gap-3 text-gray-600">
        <h3 className="text-sm font-semibold text-gray-700 mr-auto">
          Design report
        </h3>
        <input
          aria-label="Report title"
          placeholder={lens.name || "Title"}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          className="w-44 border border-gray-200 rounded px-1 py-0.5"
        />
        <input
          aria-label="Author"
          placeholder="Author"
          value={author}
          onChange={(e) => setAuthor(e.target.value)}
          className="w-28 border border-gray-200 rounded px-1 py-0.5"
        />
        {(
          [
            ["MTF", mtf, setMtf],
            ["Tolerances", tolerances, setTolerances],
            ["Drawings", drawings, setDrawings],
          ] as const
        ).map(([label, value, set]) => (
          <label key={label} className="flex items-center gap-1">
            <input
              type="checkbox"
              aria-label={label}
              checked={value}
              onChange={(e) => set(e.target.checked)}
            />
            {label}
          </label>
        ))}
        <button
          onClick={generate}
          disabled={running}
          className="px-3 py-1 bg-optical-600 text-white rounded hover:bg-optical-700 disabled:opacity-50"
        >
          {running ? "Generating..." : "Generate"}
        </button>
      </div>
      {error && (
        <p className="text-red-500" role="alert">
          {error}
        </p>
      )}
      {html && (
        <>
          <div className="flex items-center gap-2">
            <button
              onClick={savePdf}
              className="px-2 py-1 border border-gray-200 rounded hover:bg-gray-50"
            >
              Save PDF
            </button>
            <button
              onClick={saveHtml}
              className="px-2 py-1 border border-gray-200 rounded hover:bg-gray-50"
            >
              Save HTML
            </button>
            {message && <span className="text-green-700">{message}</span>}
          </div>
          <iframe
            ref={frame}
            title="Report preview"
            srcDoc={html}
            sandbox="allow-same-origin allow-modals"
            className="w-full h-[36rem] border border-gray-200 rounded bg-white"
          />
        </>
      )}
    </div>
  );
}
