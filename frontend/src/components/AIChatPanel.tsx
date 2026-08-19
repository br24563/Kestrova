/**
 * AI Chat Panel.
 *
 * Allows the user to interact with the optical system using natural
 * language. The prompt is interpreted into structured commands by the
 * backend, then executed against the optics engine.
 */

import { useEffect, useState } from "react";
import type { OpticalSystem } from "../types";
import { interpretPrompt, executeAICommand, getAIProvider, type AICommandResponse, type AIProviderInfo } from "../api";

interface AIChatPanelProps {
  system: OpticalSystem;
  onSystemUpdate: (system: OpticalSystem) => void;
}

interface ChatMessage {
  role: "user" | "assistant";
  text: string;
}

export function AIChatPanel({ system, onSystemUpdate }: AIChatPanelProps) {
  const [prompt, setPrompt] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const [provider, setProvider] = useState<AIProviderInfo | null>(null);

  useEffect(() => {
    getAIProvider()
      .then(setProvider)
      .catch(() => setProvider(null));
  }, []);

  const handleSend = async () => {
    const text = prompt.trim();
    if (!text || busy) return;

    setPrompt("");
    setMessages((prev) => [...prev, { role: "user", text }]);
    setBusy(true);

    try {
      const interpreted = await interpretPrompt(system, text);

      let currentSystem = system;
      const responses: AICommandResponse[] = [];

      for (const command of interpreted.commands) {
        const result = await executeAICommand(currentSystem, command);
        responses.push(result);
        currentSystem = result.system;
      }

      onSystemUpdate(currentSystem);

      const summary = responses.map((r) => r.message).join(" ");
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: summary || `Executed ${interpreted.commands.length} command(s).` },
      ]);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "AI request failed";
      setMessages((prev) => [...prev, { role: "assistant", text: `Error: ${msg}` }]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="p-4 border-t border-gray-200">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-medium text-gray-700">AI Assistant</h3>
        {provider && (
          <span className="text-[10px] text-gray-500 bg-gray-100 rounded px-1.5 py-0.5">
            {provider.use_ollama ? `Ollama (${provider.model})` : "Rule-based parser"}
          </span>
        )}
      </div>

      <div className="space-y-2 mb-3 max-h-48 overflow-y-auto">
        {messages.length === 0 && (
          <p className="text-xs text-gray-500">
            Try: "move lens_1 to 150mm", "set object height to 5mm", or "analyze the system"
          </p>
        )}
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`p-2 rounded text-xs ${
              msg.role === "user"
                ? "bg-optical-50 border border-optical-200"
                : "bg-gray-50 border border-gray-200"
            }`}
          >
            <span className="font-medium text-gray-600">
              {msg.role === "user" ? "You: " : "AI: "}
            </span>
            {msg.text}
          </div>
        ))}
      </div>

      <div className="flex gap-1">
        <input
          type="text"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") handleSend();
          }}
          placeholder="Ask the AI to modify the system..."
          className="flex-1 px-2 py-1 border border-gray-300 rounded text-sm"
          disabled={busy}
        />
        <button
          onClick={handleSend}
          disabled={busy || !prompt.trim()}
          className="px-3 py-1 bg-optical-600 text-white text-xs rounded hover:bg-optical-700 disabled:opacity-50"
        >
          {busy ? "..." : "Send"}
        </button>
      </div>
    </div>
  );
}