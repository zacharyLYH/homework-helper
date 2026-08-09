# Playwright MCP notes

The app is served from the production build with `vite preview` on port `4173`.
All API requests are intercepted by `base.fixture.ts`, so no backend, cookies, or
environment secrets are needed when driving the app.
