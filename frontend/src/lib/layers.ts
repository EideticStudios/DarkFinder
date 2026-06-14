export type LayerId = 'emission' | 'skyglow'

export interface LayerInfo {
  id: LayerId
  label: string
}

export const LAYERS: LayerInfo[] = [
  { id: 'skyglow', label: 'Sky Glow' },
  { id: 'emission', label: 'Emission' },
]
