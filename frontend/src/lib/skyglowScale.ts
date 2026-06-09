export interface SkyglowStop {
  value: number
  color: string
  label: string
}

export const SKYGLOW_SCALE: SkyglowStop[] = [
  { value: 0.01, color: '#02022E', label: 'Pristine' },
  { value: 0.04, color: '#0B1E8C', label: '0.04' },
  { value: 0.12, color: '#1E64DC', label: '0.12' },
  { value: 0.35, color: '#00C8C8', label: '0.35' },
  { value: 1.0,  color: '#28B428', label: '1.0' },
  { value: 3.0,  color: '#F0F000', label: '3.0' },
  { value: 8.0,  color: '#FF8C00', label: '8.0' },
  { value: 20.0, color: '#FF1E1E', label: '20' },
  { value: 45.0, color: '#FF50FF', label: '45' },
  { value: 100.0, color: '#FFFFFF', label: 'Inner city' },
]
