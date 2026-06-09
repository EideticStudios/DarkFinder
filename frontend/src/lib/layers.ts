export type LayerId = 'emission' | 'skyglow'

export interface LayerInfo {
  id: LayerId
  label: string
}

export const LAYERS: LayerInfo[] = [
  { id: 'emission', label: 'Emission' },
  { id: 'skyglow', label: 'Sky Glow' },
]
