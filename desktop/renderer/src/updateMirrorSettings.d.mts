export interface ParsedMirrorList {
  values: string[];
  errors: string[];
}

export function parseMirrorList(text: unknown): ParsedMirrorList;
export function formatMirrorList(list: unknown): string;
