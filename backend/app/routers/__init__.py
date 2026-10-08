"""HTTP routers.

A router owns HTTP and nothing else: path and method, request and response pydantic
models, authentication and authorization dependencies, status codes, and turning a
typed domain error into an HTTP response. A router contains no business rule and
issues no SQL — every domain rule and every query lives in `app.services`, which the
router calls with plain arguments. Dependency direction is one-way,
`routers -> services -> db`; nothing in `app.services` imports from here, and
`app.models` is imported by both and imports neither.
"""
