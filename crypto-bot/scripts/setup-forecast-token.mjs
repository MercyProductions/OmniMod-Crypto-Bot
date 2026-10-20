import { randomBytes } from 'node:crypto';
import { readFile, writeFile, rename } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

const file = fileURLToPath(new URL('../.env', import.meta.url));
let content = '';
try { content = await readFile(file, 'utf8'); } catch (error) { if (error.code !== 'ENOENT') throw error; }
const existing = content.match(/^CRYPTO_FORECAST_TOKEN[ \t]*=[ \t]*(.*)$/m);
if (existing?.[1].trim()) {
  console.log('Existing local research token preserved. No value displayed.');
} else {
  const line = `CRYPTO_FORECAST_TOKEN=${randomBytes(48).toString('hex')}`;
  content = existing ? content.replace(/^CRYPTO_FORECAST_TOKEN[ \t]*=.*$/m, line) : `${content.trimEnd()}\n${line}\n`;
  const temporary = `${file}.forecast-token.pending`;
  await writeFile(temporary, content, { mode: 0o600 }); await rename(temporary, file);
  console.log('Local research token initialized in the ignored .env. No value displayed.');
}
