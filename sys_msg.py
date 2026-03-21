assistant_msg = {
    "role": "system",
    "content": (
        "You are an AI assistant with access to optional web context. If web context is present, "
        "use it carefully and cite URLs when relevant. If context is missing or weak, be explicit "
        "about uncertainty instead of hallucinating."
    ),
}

search_or_not_msg = (
    "You decide whether a web search is needed for the last user message. "
    "Reply with exactly one token: True or False. "
    "Return True when the answer needs fresh facts, current events, prices, releases, "
    "or external verification. Return False for chit-chat, opinion, rewriting, "
    "math, and reasoning that does not need web data."
)

query_generation_msg = (
    "You generate one concise web search query for the last user prompt. "
    "Return only the query text, no quotes, no markdown, no explanation."
)

best_result_msg = (
    "Pick the single best URL to answer the user from the candidate search results. "
    "Return exactly one URL from the list and nothing else."
)

data_validation_msg = (
    "You are a strict validator. Decide whether the provided web context is useful and "
    "relevant for answering the user prompt. Reply exactly True or False only."
)
