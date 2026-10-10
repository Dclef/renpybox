import { open } from 'node:fs/promises';

const MAX_BYTES = 256 * 1024;
const MAX_LINES = 2000;

/** Read a bounded tail without modifying logs or cutting a UTF-8 character. */
export async function readLogTail(filename) {
  let file;
  try { file = await open(filename, 'r'); }
  catch (error) {
    if (error.code === 'ENOENT') return { text: '', truncated: false };
    throw error;
  }
  try {
    const { size } = await file.stat();
    const start = Math.max(0, size - MAX_BYTES);
    const buffer = Buffer.alloc(Math.min(size, MAX_BYTES));
    let length = 0;
    while (length < buffer.length) {
      const { bytesRead } = await file.read(buffer, length, buffer.length - length, start + length);
      if (!bytesRead) break;
      length += bytesRead;
    }
    let data = buffer.subarray(0, length);
    let truncated = start > 0;
    if (start > 0) {
      const previousByte = Buffer.alloc(1);
      const { bytesRead } = await file.read(previousByte, 0, 1, start - 1);
      // Keep a complete first line when the byte limit lands just after LF.
      if (bytesRead !== 1 || previousByte[0] !== 10) {
        const newline = data.indexOf(10);
        if (newline >= 0) data = data.subarray(newline + 1);
        else {
          let offset = 0;
          while (offset < data.length && (data[offset] & 0xc0) === 0x80) offset += 1;
          data = data.subarray(offset);
        }
      }
    }
    // A writer can be midway through its last UTF-8 character. The next refresh
    // will include it; do not show a replacement character in this snapshot.
    const decoder = new TextDecoder('utf-8');
    const text = decoder.decode(data, { stream: true });
    const lines = text.split(String.fromCharCode(10));
    const trailingNewline = lines.at(-1) === '';
    if (trailingNewline) lines.pop();
    if (lines.length > MAX_LINES) { lines.splice(0, lines.length - MAX_LINES); truncated = true; }
    return { text: lines.join(String.fromCharCode(10)) + (trailingNewline && lines.length ? String.fromCharCode(10) : ''), truncated };
  } finally { await file.close(); }
}
