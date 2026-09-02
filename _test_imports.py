import sys, traceback
sys.stdout.reconfigure(encoding='utf-8')

modules = [
    ('agents.state', 'from agents.state import TourState, TripIntent'),
    ('agents.base', 'from agents.base import BaseTourAgent'),
    ('agents.intent_agent', 'from agents.intent_agent import IntentAgent'),
    ('agents.retrieve_agent', 'from agents.retrieve_agent import RetrieveAgent'),
    ('agents.poi_agent', 'from agents.poi_agent import PoiAgent'),
    ('agents.hotel_agent', 'from agents.hotel_agent import HotelAgent'),
    ('agents.weather_agent', 'from agents.weather_agent import WeatherAgent'),
    ('agents.restaurant_agent', 'from agents.restaurant_agent import RestaurantAgent'),
    ('agents.scheduler_agent', 'from agents.scheduler_agent import SchedulerAgent'),
    ('agents.reviewer_agent', 'from agents.reviewer_agent import ReviewerAgent'),
    ('agents.ticket_agent', 'from agents.ticket_agent import TicketAgent'),
    ('tools.rag', 'from tools import rag'),
    ('tools.weather_api', 'from tools import weather_api'),
    ('tools.scoring', 'from tools.scoring import rank_pois'),
    ('tools.clustering', 'from tools.clustering import cluster_pois_for_days'),
    ('tools.route', 'from tools.route import optimize_route, optimize_route_2opt'),
    ('graph', 'from graph import build_tour_graph, create_initial_state'),
]

ok = 0
fail = 0
for name, stmt in modules:
    try:
        exec(stmt)
        print(f'  OK  {name}')
        ok += 1
    except Exception as e:
        print(f'  FAIL {name}: {e}')
        fail += 1

print(f'\nResult: {ok} OK, {fail} FAIL out of {len(modules)}')
