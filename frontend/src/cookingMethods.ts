export const COOKING_METHODS = ['stir_fry', 'steam', 'boil', 'stew', 'bake', 'pan_fry', 'cold', 'other'] as const;
export type CookingMethod = (typeof COOKING_METHODS)[number];
export const MAX_METHODS = 3;

const label: Record<string, string> = {stir_fry:'炒', steam:'蒸', boil:'煮', stew:'炖',
 bake:'烤', pan_fry:'煎', cold:'凉拌', other:'其他'};
export const methodName = (value: string): string => label[value] || value;
export const isCookingMethod = (value: unknown): value is CookingMethod =>
 typeof value === 'string' && (COOKING_METHODS as readonly string[]).includes(value);

// A draft may still hold a value outside the vocabulary; it has to stay visible to be fixable.
// Blanks are dropped because the server skips them too, so the page never shows an empty tag.
export function methodsFromStored(value: unknown): string[] {
 if (!Array.isArray(value)) return [];
 return value.map(x => typeof x === 'string' || typeof x === 'number' ? String(x).trim() : '')
  .filter(Boolean);
}

export function toggleMethod(selected: string[], value: string): string[] {
 if (selected.includes(value)) return selected.filter(x => x !== value);
 if (selected.length >= MAX_METHODS) return selected;
 return [...selected, value];
}

export function methodText(methods: string[]): string {
 return methods.map(methodName).join(' / ');
}
