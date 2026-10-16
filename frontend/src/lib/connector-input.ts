/** Structured argv preserves spaces, quotes and Windows paths without a shell. */
export function parseArguments(text: string): string[] {
  const value: unknown = text.trim() ? JSON.parse(text) : [];
  if (!Array.isArray(value) || value.length > 255 || value.some(v => typeof v !== 'string' || v.includes('\0'))) {
    throw new Error('Argumentos: use una lista JSON de textos, por ejemplo ["--version"].');
  }
  return value;
}

export function parseEnvironment(text: string): Record<string, string> {
  const value: unknown = text.trim() ? JSON.parse(text) : {};
  if (!value || typeof value !== 'object' || Array.isArray(value) || Object.entries(value).some(
    ([key, val]) => !/^[A-Za-z_][A-Za-z0-9_]*$/.test(key) || typeof val !== 'string' || val.includes('\0'),
  )) throw new Error('Variables: use un objeto JSON con nombres y valores de texto.');
  return value as Record<string, string>;
}
