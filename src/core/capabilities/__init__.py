"""The business capabilities the supervisor routes between.

Renamed from `subgraphs/`, which named a LangGraph implementation detail and was
inaccurate besides: only `user/` is an actual nested StateGraph -- the others are
single node functions. The routing machinery that dispatches *to* these lives in
`core/orchestration/routing/`.
"""
