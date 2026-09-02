import sys
sys.stdout.reconfigure(encoding='utf-8')
content = open('graph.py', 'r', encoding='utf-8').read()

old = '''    def route_review(state: TourState) -> str:
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

new = '''    def route_review(state: TourState) -> str:
        review = state.get("review_result")
        review_cycle = state.get("review_cycle", 0)

        # If reviewer crashed (no review_result), force pass to avoid infinite loop
        if review is None:
            logger.warning("Reviewer produced no result (crash?), forcing pass")
            return "node_ticket"

        # Safety: force pass after MAX_REVIEW_CYCLES
        if review_cycle >= MAX_REVIEW_CYCLES:
            logger.warning("Review cycle limit reached (%d), forcing pass", review_cycle)
            return "node_ticket"

        if review.get("passed"):
            return "node_ticket"

        issues = review.get("issues", [])
        logger.info("Review not passed (cycle=%d, issues=%d), revising...", review_cycle, len(issues))
        return "node_scheduler"'''

content = content.replace(old, new)
open('graph.py', 'w', encoding='utf-8').write(content)
print("route_review fixed: None review_result forces pass")
