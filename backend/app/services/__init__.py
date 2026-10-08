"""Domain services.

A service owns domain rules and data access. It takes plain arguments and returns
plain results or raises a typed domain error; it never imports `fastapi`, never sees
a `Request` and never knows a status code, so it is testable without a transport and
all SQL sits in one auditable layer. Dependency direction is one-way,
`routers -> services -> db`; a service never imports from `app.routers`.
"""
