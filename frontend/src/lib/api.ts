// Reads VITE_API_BASE at build time; falls back to localhost for dev.
export const API_BASE =
  import.meta.env.VITE_API_BASE ?? 'http://localhost:8000/api/v1'
