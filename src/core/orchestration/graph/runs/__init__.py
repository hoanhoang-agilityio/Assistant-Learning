"""Run-orchestration support modules.

Extracted from the 1,209-line graph/service.py so the transport-facing DTOs and
the pure checkpoint->status projection helpers are findable on their own.
RunOrchestrator itself still lives in graph/service.py -- see that module's
docstring for why the remaining concerns were not split further.
"""
