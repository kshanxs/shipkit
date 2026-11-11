---
name: wire-api
description: "The protocol for wiring a screen (web or mobile) to an API endpoint without drift: read the route and schemas first, send the auth and (when multi-tenant) tenant headers through the one client, mirror or generate the response types from OpenAPI, key queries by everything they depend on, invalidate after writes, keep mocks typed to the contract, and move the tracker's status (Frontend only, Backend only, Built). Use when connecting a screen to an endpoint, replacing a mock with the real API, adding an endpoint a screen needs, and when the user says 'wire', 'hook up', 'connect to the API', 'real API', 'frontend only', 'backend only', 'unhooked', 'contract' or 'OpenAPI'."
---

# Wire a screen to the API

The contract between a front end and the API, and the steps that keep them from drifting: no
invented routes, no hand-guessed fields, no untracked gaps. Works with stack-backend, stack-web,
stack-native and docsync.

## The three states

Every feature's API is in one of three states, kept in the tracker (`docs/feature_status.md`):

| State | Means | Your job |
|---|---|---|
| **Built** | The route exists and a screen calls it | Verify the round trip, the tenant headers and the tests |
| **Frontend only** | The screen works against a mock; the route does not exist | Never call a route that does not exist. Keep the mock typed to the agreed contract, and say "Frontend only" in the tracker |
| **Backend only** | The route exists with schemas and tests; no screen calls it | Read its schemas and wire the live endpoint |

## Five steps

### 1. Read the contract

Open the route and its schemas (`app/<module>/router.py` and `schemas.py`, or the controller and
its zod schemas). Write down: the method, the full path, the status codes (201 against 200), the
query parameters and body, and the error codes (400, 401, 403, 404, 409, 422).

### 2. Auth and tenant headers

A route that needs credentials gets the auth token (or session cookie) from the one API client's
interceptor, never set by hand in a component. **[multi-tenant]** A tenant-scoped route also needs
the tenant header (for example `X-Workspace-ID`), through the same interceptor; skip it when the
project profile (`project.py show`) is not multi-tenant.

### 3. Types and the client call

Prefer generated types: export the OpenAPI document, then generate (`openapi-typescript` or the
project's script) and commit the generated file; CI fails when it is stale. If types are written by
hand, mirror the schema exactly: field names, nullability (`X | None` becomes `X | null`), enum
strings. No client-only fields.

```typescript
import { api } from '@/lib/api'
import type { components } from '@/types/api.gen'

export type Project = components['schemas']['ProjectOut']

export const listProjects = async (params?: { page?: number }): Promise<Project[]> =>
  (await api.get<Project[]>('/projects', { params })).data
```

### 4. Queries and invalidation

```typescript
export const projectKeys = {
  all: (workspaceId: string) => ['projects', workspaceId] as const,
  list: (workspaceId: string, filters: ProjectFilters) => [...projectKeys.all(workspaceId), 'list', filters] as const,
}

export const useCreateProject = () => {
  const queryClient = useQueryClient()
  const workspaceId = useWorkspaceId()
  return useMutation({
    mutationFn: createProject,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: projectKeys.all(workspaceId) }),
  })
}
```

Keys include every input the answer depends on (tenant, user or role where it matters, filters,
ids). Every screen has its loading, empty and error states.

### 5. Documents, in the same sitting

The app's changelog line, the feature's spec, its tracker row moved to **Built** (or the state it
is in), and `check_docs.py --changed` (docsync).

## When the two sides disagree

**The screen needs a route that does not exist.** Do not fake the answer inside the component. Add
a typed mock (an MSW handler or the app's mock layer), mark the tracker **Frontend only** with the
note "screens built against a mock; waiting for the route", and give the route's agreed shape in
the spec so the backend can build to it.

**A route exists with no screen and no document.** Find it in the router, check the spec's code
map, and mark the tracker **Backend only** until a screen and its query hook are wired and tested.

**A generated contract changed.** Change the API's schema first, export, regenerate, update the mock
to the same shape (a test that checks every mock answer against the contract catches drift), then
typecheck and test.
