export interface BortleClass {
  class: number;
  label: string;
  description: string;
  color: string;
  minRadiance: number;
  maxRadiance: number | null;
}

// Colors mirror the shared RAMP_COLORS in backend/app/services/tile_renderer.py —
// keep the two in sync.
export const BORTLE_SCALE: BortleClass[] = [
  { class: 1, label: 'Class 1', description: 'Pristine dark sky',   color: '#02022E', minRadiance: 0.0,  maxRadiance: 0.2  },
  { class: 2, label: 'Class 2', description: 'Typical dark site',   color: '#0B1E8C', minRadiance: 0.2,  maxRadiance: 0.4  },
  { class: 3, label: 'Class 3', description: 'Rural sky',           color: '#1E64DC', minRadiance: 0.4,  maxRadiance: 1.0  },
  { class: 4, label: 'Class 4', description: 'Rural / suburban',    color: '#00C8C8', minRadiance: 1.0,  maxRadiance: 3.0  },
  { class: 5, label: 'Class 5', description: 'Suburban sky',        color: '#28B428', minRadiance: 3.0,  maxRadiance: 6.0  },
  { class: 6, label: 'Class 6', description: 'Bright suburban',     color: '#F0F000', minRadiance: 6.0,  maxRadiance: 12.0 },
  { class: 7, label: 'Class 7', description: 'Suburban / urban',    color: '#FF8C00', minRadiance: 12.0, maxRadiance: 30.0 },
  { class: 8, label: 'Class 8', description: 'City sky',            color: '#FF1E1E', minRadiance: 30.0, maxRadiance: 60.0 },
  { class: 9, label: 'Class 9', description: 'Inner-city sky',      color: '#FF50FF', minRadiance: 60.0, maxRadiance: null },
];
