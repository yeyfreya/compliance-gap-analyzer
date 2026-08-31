"""
Tools for AI Compliance Gap Analyzer
search + utility functions used by the agent

Agent Workflow:
1. User Input
2. Plan Research (Claude) → prompts.py
3. Execute Research (Tavily) → tools.py ← THIS FILE
4. Analyze Findings (Claude) → prompts.py
5. Output Report
"""


import os
import time
from tavily import TavilyClient
from dotenv import load_dotenv
from langfuse import observe  # records each search as its own step in Langfuse

# Load environment variables
load_dotenv()

# Initialize Tavily client once (reused for all searches)
# DESIGN DECISION: Created at file level for efficiency
tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))


#search_web() - Use Tavily to search the web for information
@observe()
def search_web(query: str, max_results: int = 3, include_domains: list[str] | None = None) -> dict:
    """
    Search the web for compliance-related information.

    Args:
        query: Search query string (e.g., "HIPAA requirements for AI")
        max_results: Maximum number of results to return (default: 3)
        include_domains: Optional list of domains to restrict the search to (v0.7 —
            Tier 1 official-source-first search). When falsy, omitted from the Tavily
            call entirely, so unrestricted callers see no behavior change.

    Returns:
        Dictionary with 'results' list, or 'error' key if search fails
    """

    last_error = None
    for attempt in range(2):
        try:
            print(f"\n🔍 Searching: {query}")

            search_kwargs = {
                "query": query,
                "max_results": max_results,
                "search_depth": "advanced",
            }
            if include_domains:
                search_kwargs["include_domains"] = include_domains

            response = tavily.search(**search_kwargs)

            results = []
            for result in response.get('results', []):
                results.append({
                    'title': result.get('title', ''),
                    'url': result.get('url', ''),
                    'content': result.get('content', '')[:500]
                })
            
            print(f"\n🔍 Found {len(results)} results")
            return {'results': results}

        except Exception as e:
            last_error = e
            if attempt == 0:
                print(f"\n⚠️ Search failed (attempt 1/2), retrying in 2s…")
                time.sleep(2)
            else:
                print(f"\n❌ Search failed after retry: {str(e)}")

    return {'results': [], 'error': str(last_error)}


def format_search_results(search_results: list) -> str:
    """
    Format search results into readable text for Claude.

    Args:
        search_results: List of search result dictionaries from search_web()

    Returns:
        Formatted string combing all results
    """

    if not search_results:
        return "No search results found"

    formatted = []

    for i, result in enumerate(search_results, 1):
        formatted.append(f"\n --- Result {i} ---")
        formatted.append(f"Title: {result.get('title', 'N/A')}")
        formatted.append(f"URL: {result.get('url', 'N/A')}")
        formatted.append(f"Content: {result.get('content', 'N/A')}")

    return "\n".join(formatted)



