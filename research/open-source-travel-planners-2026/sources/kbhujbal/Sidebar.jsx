import { Clock, Trash2, MapPin, X } from "lucide-react";

export default function Sidebar({ history, onSelect, onDelete, isOpen, onClose }) {
  return (
    <>
      {/* Overlay for mobile */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/30 z-40 lg:hidden"
          onClick={onClose}
        />
      )}

      <aside
        className={`fixed lg:static inset-y-0 left-0 z-50 w-72 bg-white border-r border-slate-200 flex flex-col transform transition-transform duration-200 ${
          isOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"
        }`}
      >
        <div className="p-4 border-b border-slate-200 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Clock size={16} className="text-slate-500" />
            <h2 className="text-sm font-semibold text-slate-700">History</h2>
          </div>
          <button
            onClick={onClose}
            className="p-1 hover:bg-slate-100 rounded lg:hidden"
          >
            <X size={16} className="text-slate-500" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-2">
          {history.length === 0 ? (
            <div className="text-center py-8 px-4">
              <MapPin size={32} className="text-slate-300 mx-auto mb-2" />
              <p className="text-sm text-slate-400">
                No trips planned yet.
              </p>
              <p className="text-xs text-slate-400 mt-1">
                Your itineraries will appear here.
              </p>
            </div>
          ) : (
            <div className="space-y-1">
              {history.map((item) => (
                <div
                  key={item.id}
                  className="group flex items-start gap-2 p-2.5 rounded-lg hover:bg-slate-50 cursor-pointer transition-colors"
                  onClick={() => {
                    onSelect(item);
                    onClose();
                  }}
                >
                  <MapPin
                    size={14}
                    className="text-slate-400 mt-0.5 shrink-0"
                  />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-slate-700 truncate">
                      {item.request.slice(0, 60)}
                      {item.request.length > 60 ? "..." : ""}
                    </p>
                    <p className="text-xs text-slate-400 mt-0.5">
                      {new Date(item.created_at).toLocaleDateString()}
                      {" · "}
                      <span
                        className={
                          item.status === "completed"
                            ? "text-green-500"
                            : item.status === "processing"
                            ? "text-blue-500"
                            : "text-red-500"
                        }
                      >
                        {item.status}
                      </span>
                    </p>
                  </div>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onDelete(item.id);
                    }}
                    className="opacity-0 group-hover:opacity-100 p-1 hover:bg-red-50 rounded text-slate-400 hover:text-red-500 transition-all"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </aside>
    </>
  );
}

