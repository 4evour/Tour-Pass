import { useState, useEffect } from "react";
import Header from "./components/Header";
import Sidebar from "./components/Sidebar";
import ChatInput from "./components/ChatInput";
import TripDetailsForm from "./components/TripDetailsForm";
import AgentProgress from "./components/AgentProgress";
import ItineraryDisplay from "./components/ItineraryDisplay";
import WelcomeScreen from "./components/WelcomeScreen";
import { useWebSocket } from "./hooks/useWebSocket";
import { useItineraryHistory } from "./hooks/useItineraryHistory";
import { AlertCircle } from "lucide-react";

// App flow: idle -> form -> processing -> completed
//                       \-> error

export default function App() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [tripIdea, setTripIdea] = useState("");       // Step 1: user's free-text idea
  const [currentRequest, setCurrentRequest] = useState(""); // Full structured prompt sent to backend
  const [selectedItinerary, setSelectedItinerary] = useState(null);

  const {
    status,
    agents,
    agentProgress,
    itinerary,
    error,
    sendRequest,
    reset,
  } = useWebSocket();

  const { history, fetchHistory, deleteItinerary } = useItineraryHistory();

  useEffect(() => {
    if (status === "completed") {
      fetchHistory();
    }
  }, [status, fetchHistory]);

  // Step 1: User types trip idea -> show details form
  const handleTripIdea = (message) => {
    setSelectedItinerary(null);
    setTripIdea(message);
  };

  // Step 2: User fills details form -> send to backend
  const handleDetailsSubmit = (structuredPrompt) => {
    setCurrentRequest(structuredPrompt);
    sendRequest(structuredPrompt);
  };

  // Go back from form to input
  const handleBackToInput = () => {
    setTripIdea("");
  };

  const handleSelectHistory = (item) => {
    reset();
    setTripIdea("");
    setSelectedItinerary(item);
    setCurrentRequest(item.request);
  };

  const handleNewTrip = () => {
    reset();
    setTripIdea("");
    setSelectedItinerary(null);
    setCurrentRequest("");
  };

  const isProcessing = status === "processing" || status === "connecting";
  const showForm = tripIdea && status === "idle" && !selectedItinerary;
  const showWelcome = status === "idle" && !tripIdea && !selectedItinerary;
  const showItinerary =
    (status === "completed" && itinerary) ||
    (selectedItinerary && selectedItinerary.status === "completed");

  const displayedItinerary = selectedItinerary
    ? selectedItinerary.itinerary
    : itinerary;
  const displayedRequest = selectedItinerary
    ? selectedItinerary.request
    : currentRequest;

  return (
    <div className="h-screen flex flex-col bg-slate-50">
      <Header onToggleSidebar={() => setSidebarOpen(!sidebarOpen)} />

      <div className="flex flex-1 overflow-hidden">
        <Sidebar
          history={history}
          onSelect={handleSelectHistory}
          onDelete={deleteItinerary}
          isOpen={sidebarOpen}
          onClose={() => setSidebarOpen(false)}
        />

        <main className="flex-1 flex flex-col overflow-hidden">
          {/* Scrollable content area */}
          <div className="flex-1 overflow-y-auto">
            {showWelcome && <WelcomeScreen />}

            {/* Step 2: Trip details form */}
            {showForm && (
              <TripDetailsForm
                tripIdea={tripIdea}
                onSubmit={handleDetailsSubmit}
                onBack={handleBackToInput}
                disabled={false}
              />
            )}

            {/* Error message */}
            {status === "error" && error && (
              <div className="mx-4 mt-4">
                <div className="bg-red-50 border border-red-200 rounded-xl p-4 flex items-start gap-3">
                  <AlertCircle size={20} className="text-red-500 shrink-0 mt-0.5" />
                  <div>
                    <p className="text-sm font-medium text-red-800">
                      Something went wrong
                    </p>
                    <p className="text-sm text-red-600 mt-1">{error}</p>
                    <button
                      onClick={handleNewTrip}
                      className="text-sm text-red-700 underline mt-2 hover:text-red-800"
                    >
                      Try again
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* Agent progress */}
            {isProcessing && (
              <AgentProgress agents={agents} agentProgress={agentProgress} />
            )}

            {/* Itinerary display */}
            {showItinerary && (
              <ItineraryDisplay
                itinerary={displayedItinerary}
                request={displayedRequest}
              />
            )}

            {/* New trip button */}
            {(showItinerary || status === "error") && (
              <div className="text-center py-4">
                <button
                  onClick={handleNewTrip}
                  className="bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium px-6 py-2.5 rounded-xl transition-colors"
                >
                  Plan Another Trip
                </button>
              </div>
            )}
          </div>

          {/* Step 1: Chat input — only visible when no form is showing */}
          {!showForm && (
            <ChatInput onSend={handleTripIdea} disabled={isProcessing} />
          )}
        </main>
      </div>
    </div>
  );
}

