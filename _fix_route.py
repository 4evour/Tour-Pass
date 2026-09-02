import sys
sys.stdout.reconfigure(encoding='utf-8')

content = open('graph.py', 'r', encoding='utf-8').read()

old_route = '''    # Conditional edge: reviewer -> ticket (pass) or scheduler (revise)
    def route_review(state: TourState) -> str:
        review = state.get("review_result") or {}
        errors = state.get("errors", [])

        # Count review cycles to prevent infinite loops
        review_count = sum(
            1 for e in errors if "review" in e.lower() or "Schedule creation failed" in e
        )

        if review_count >= MAX_REVIEW_CYCLES:
            logger.warning("Review cycle limit reached (%d), forcing pass", review_count)
            return "node_ticket"

        if review.get("passed"):
            return "node_ticket"

        logger.info("Review not passed (issues: %d), revising...", len(review.get("issues", [])))
        return "node_scheduler"'''

new_route = '''    # Conditional edge: reviewer -> ticket (pass) or scheduler (revise)
    def route_review(state: TourState) -> str:
        review = state.get("review_result") or {}
        review_cycle = state.get("review_cycle", 0)

        # Safety: force pass after MAX_REVIEW_CYCLES
        if review_cycle >= MAX_REVIEW_CYCLES:
            logger.warning("Review cycle limit reached (%d), forcing pass", review_cycle)
            return "node_ticket"

        if review.get("passed"):
            return "node_ticket"

        issues = review.get("issues", [])
        logger.info("Review not passed (cycle=%d, issues=%d), revising...", review_cycle, len(issues))
        return "node_scheduler"'''

content = content.replace(old_route, new_route)

with open('graph.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("graph.py route_review patched to use review_cycle counter")
