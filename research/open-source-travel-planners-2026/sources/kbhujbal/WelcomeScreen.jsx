import { Globe, Plane, Hotel, MapPin, Sparkles } from "lucide-react";

const FEATURES = [
  { icon: Plane, title: "Flight Search", desc: "Finds optimal flight options" },
  { icon: Hotel, title: "Hotel Booking", desc: "Curates perfect accommodations" },
  { icon: MapPin, title: "Activities", desc: "Discovers tours & experiences" },
  { icon: Sparkles, title: "AI Powered", desc: "7 specialized agents collaborate" },
];

export default function WelcomeScreen() {
  return (
    <div className="flex-1 flex flex-col items-center justify-center p-8 text-center">
      <div className="bg-blue-100 p-4 rounded-2xl mb-4">
        <Globe size={40} className="text-blue-600" />
      </div>
      <h2 className="text-2xl font-bold text-slate-900 mb-2">
        Plan Your Dream Trip
      </h2>
      <p className="text-slate-500 max-w-md mb-8">
        Describe your ideal vacation and our AI agents will research flights,
        hotels, activities, and create a detailed day-by-day itinerary.
      </p>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 max-w-lg">
        {FEATURES.map(({ icon: Icon, title, desc }) => (
          <div
            key={title}
            className="bg-white border border-slate-200 rounded-xl p-4 text-center"
          >
            <Icon size={24} className="text-blue-600 mx-auto mb-2" />
            <p className="text-sm font-medium text-slate-800">{title}</p>
            <p className="text-xs text-slate-500 mt-1">{desc}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

