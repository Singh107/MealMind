import { apiUrl } from './apiConfig';

export interface Detection {
  display_name: string; confidence: 'high' | 'medium' | 'low'; visible_state: string | null;
  uncertainty: string; normalized_name: string; canonical_name: string | null;
  food_state: string | null; identity_status: 'recognized' | 'unresolved' | 'conflicting'; merged_count: number;
}
export interface ImageAnalysis { analysis_id: string; detections: Detection[]; warnings: string[]; provider: string; model: string }

export async function requestImage<T>(file: File, signal: AbortSignal, path: string, validate: (value: any) => boolean): Promise<T> {
  const controller = new AbortController();
  const abort = () => controller.abort();
  signal.addEventListener('abort', abort);
  if (signal.aborted) controller.abort();
  const timer = window.setTimeout(abort, 65000);
  try {
    const response = await fetch(apiUrl(path), {
      method: 'POST', headers: { 'Content-Type': file.type }, body: file, signal: controller.signal,
    });
    if (!response.ok) {
      const messages: Record<number, string> = { 413: 'Image file too large (max 5MB).', 415: 'Choose a JPEG, PNG or WebP image.',
        422: 'This photo could not be read. Choose a valid, still image.', 429: 'Ingredient analysis is busy. Please try later.',
        504: 'Ingredient analysis timed out. Please try again.' };
      throw new Error(messages[response.status] || 'Ingredient analysis is unavailable. Please try again.');
    }
    const value = await response.json();
    if (!validate(value)) throw new Error('Photo suggestions could not be read. Please try again.');
    return value;
  } catch (error) {
    if (controller.signal.aborted) throw new Error('Ingredient analysis was cancelled or timed out.');
    if (error instanceof TypeError) throw new Error('Ingredient analysis is unavailable. Please try again.');
    throw error;
  } finally { clearTimeout(timer); signal.removeEventListener('abort', abort); }
}

export function analyzeIngredients(file: File, signal: AbortSignal): Promise<ImageAnalysis> {
  return requestImage(file, signal, '/api/vision/ingredients', value => !!value && typeof value.analysis_id === 'string' &&
    Array.isArray(value.detections) && value.detections.length <= 30 && value.detections.every((d: any) =>
      typeof d.display_name === 'string' && d.display_name.trim().length > 0 && d.display_name.length <= 120 &&
      ['high','medium','low'].includes(d.confidence) && [null,'raw','cooked','dry','canned'].includes(d.visible_state) &&
      typeof d.uncertainty === 'string' && typeof d.normalized_name === 'string' &&
      ['recognized','unresolved','conflicting'].includes(d.identity_status)));
}
