import ReactMarkdown from "react-markdown";
import { Download, Copy, Check } from "lucide-react";
import { useState } from "react";

export default function ItineraryDisplay({ itinerary, request }) {
  const [copied, setCopied] = useState(false);

  if (!itinerary) return null;

  const handleCopy = async () => {
    await navigator.clipboard.writeText(itinerary);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = () => {
    const content = `# Travel Itinerary\n\n## Original Request\n\n${request}\n\n## Complete Itinerary\n\n${itinerary}`;
    const blob = new Blob([content], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "travel_itinerary.md";
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="mx-4 my-3">
      {/* Header with actions */}
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold text-slate-700">
          Your Travel Itinerary
        </h3>
        <div className="flex gap-1">
          <button
            onClick={handleCopy}
            className="p-2 hover:bg-slate-100 rounded-lg transition-colors text-slate-500 hover:text-slate-700"
            title="Copy to clipboard"
          >
            {copied ? <Check size={16} className="text-green-500" /> : <Copy size={16} />}
          </button>
          <button
            onClick={handleDownload}
            className="p-2 hover:bg-slate-100 rounded-lg transition-colors text-slate-500 hover:text-slate-700"
            title="Download as Markdown"
          >
            <Download size={16} />
          </button>
        </div>
      </div>

      {/* Original request */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 mb-3">
        <p className="text-xs font-medium text-blue-700 mb-1">Your Request</p>
        <p className="text-sm text-blue-900">{request}</p>
      </div>

      {/* Itinerary content */}
      <div className="bg-white border border-slate-200 rounded-xl p-6 itinerary-content">
        <ReactMarkdown>{itinerary}</ReactMarkdown>
      </div>
    </div>
  );
}

