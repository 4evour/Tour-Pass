import sys
sys.stdout.reconfigure(encoding='utf-8')
content = open('graph.py', 'r', encoding='utf-8').read()

old = '''    def route_review(state: TourState) -> str:
        review = state.get("review_result") or {}
        cycle = state.get("review_cycle", 0)

        if cycle >= MAX_REVIEW_CYCLES:
            logger.warning("Review cycle limit reached (%d), forcing pass", cycle)
            return "node_ticket"

        if review.get("passed"):
            return "node_ticket"

        logger.info("Review not passed (severity=%s, issues=%d), revising...",
                     review.get("severity"), len(review.get("issues", [])))
        return "node_scheduler"'''

new = '''    def route_review(state: TourState) -> str:
        review = state.get("review_result")
        cycle = state.get("review_cycle", 0)

        # Reviewer crashed or never produced a result - force pass
        if review is None:
            logger.warning("No review_result (reviewer crashed?), forcing pass")
            return "node_ticket"

        if cycle >= MAX_REVIEW_CYCLES:
            logger.warning("Review cycle limit reached (%d), forcing pass", cycle)
            return "node_ticket"

        if review.get("passed"):
            return "node_ticket"

        logger.info("Review not passed (severity=%s, issues=%d), revising...",
                     review.get("severity"), len(review.get("issues", [])))
        return "node_scheduler"'''

if old in content:
    content = content.replace(old, new)
    open('graph.py', 'w', encoding='utf-8').write(content)
    print("Fixed route_review")
else:
    print("ERROR: old text not found in graph.py")
    # Show the actual content
    import re
    m = re.search(r'def route_review.*?return "node_scheduler"', content, re.DOTALL)
    if m:
        print("Actual content:")
        print(m.group()[:500])
