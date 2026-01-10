export const GRID_SIZE = 90;
export const FIELD_SIZE = 25;
export const MAX_FP = 15;
export const TOKEN_OFFSET = 4;
export const PERCENTAGE_MAX = 100;
export const CENTER_OFFSET_X = -900;
export const CENTER_OFFSET_Y = -900;

export const STATUS_CONFIG = {
    '出血': { icon: 'bleed.png', color: '#dc3545', borderColor: '#ff0000' },
    '破裂': { icon: 'rupture.png', color: '#28a745', borderColor: '#00ff00' },
    '亀裂': { icon: 'fissure.png', color: '#007bff', borderColor: '#0000ff' },
    '戦慄': { icon: 'fear.png', color: '#17a2b8', borderColor: '#00ffff' },
    '荊棘': { icon: 'thorns.png', color: '#155724', borderColor: '#0f0' }
};

// Global Bridge for Backward Compatibility
window.GRID_SIZE = GRID_SIZE;
window.FIELD_SIZE = FIELD_SIZE;
window.MAX_FP = MAX_FP;
window.TOKEN_OFFSET = TOKEN_OFFSET;
window.PERCENTAGE_MAX = PERCENTAGE_MAX;
window.CENTER_OFFSET_X = CENTER_OFFSET_X;
window.CENTER_OFFSET_Y = CENTER_OFFSET_Y;
window.STATUS_CONFIG = STATUS_CONFIG;
