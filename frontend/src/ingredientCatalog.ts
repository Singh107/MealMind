import data from './ingredientCatalog.json';

export const ingredientCatalog = data;
export const cleanSearch = (value: string) => value.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim().replace(/\s+/g, ' ');

export function searchIngredients(query: string, limit = 10) {
  const q = cleanSearch(query);
  if (!q) return [];
  const rank = (item: typeof data[number]) => {
    const names = [cleanSearch(item.name), cleanSearch(item.canonical)];
    const aliases = item.aliases.map(cleanSearch);
    const checks = [names.includes(q), aliases.includes(q), names.some(x => x.startsWith(q)),
      aliases.some(x => x.startsWith(q)), names.some(x => x.includes(q)), aliases.some(x => x.includes(q))];
    const index = checks.indexOf(true);
    return index < 0 ? 6 : index;
  };
  const compare = (a: string, b: string) => a < b ? -1 : a > b ? 1 : 0;
  return data.filter(item => rank(item) < 6).sort((a, b) => rank(a) - rank(b) ||
    compare(cleanSearch(a.name), cleanSearch(b.name)) || compare(a.id, b.id)).slice(0, limit);
}
