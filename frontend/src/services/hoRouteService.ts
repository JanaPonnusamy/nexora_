import { api } from './apiClient'

/** A configurable HO route (dbo.ho_routes) that agents/clients discover via
 *  GET /api/bootstrap/routes. Adding the new HO's URL here while the current HO
 *  is up is how a planned HO migration propagates to every store. */
export interface HoRoute {
  route_id: number
  label: string
  url: string
  route_order: number
  is_active: boolean
  updated_at: string | null
}

export interface HoRouteInput {
  label: string
  url: string
  route_order?: number
  is_active?: boolean
}

interface RoutesResponse {
  routes: HoRoute[]
}

export const hoRouteService = {
  list: () => api.get<RoutesResponse>('/api/ho-routes').then((r) => r.routes),
  create: (input: HoRouteInput) =>
    api.post<RoutesResponse>('/api/ho-routes', input).then((r) => r.routes),
  update: (routeId: number, input: Partial<HoRouteInput>) =>
    api.put<RoutesResponse>(`/api/ho-routes/${routeId}`, input).then((r) => r.routes),
  remove: (routeId: number) =>
    api.delete<RoutesResponse>(`/api/ho-routes/${routeId}`).then((r) => r.routes),
}
