// Tiny shared state: written by app.js, read by tabs and sheets.

export const S = {
  settings: null,   // /api/settings payload (or cached copy)
  today: null,      // /api/today payload (or cached copy)
  tab: 'today',
  standalone: window.matchMedia?.('(display-mode: standalone)').matches
    || window.navigator.standalone === true,
};

export const MEAL_OPTIONS = [
  { value: 'breakfast', label: 'Breakfast' },
  { value: 'lunch', label: 'Lunch' },
  { value: 'dinner', label: 'Dinner' },
  { value: 'snack', label: 'Snack' },
];

export const ACCURACY_OPTIONS = [
  { value: 'exact_menu', label: 'Exact / menu' },
  { value: 'good_estimate', label: 'Good estimate' },
  { value: 'rough_estimate', label: 'Rough' },
];

export const TAG_OPTIONS = [
  { value: 'protein', label: 'Protein' },
  { value: 'fibre', label: 'Fibre' },
  { value: 'wholegrain', label: 'Wholegrain' },
  { value: 'fruit', label: 'Fruit' },
  { value: 'vegetables', label: 'Vegetables' },
  { value: 'low_energy', label: 'Low-energy (free)' },
];
