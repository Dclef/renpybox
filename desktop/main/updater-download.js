import { createHash } from 'node:crypto';
import { createWriteStream } from 'node:fs';
import { mkdir, rename, rm } from 'node:fs/promises';
import path from 'node:path';
import { Readable, Transform } from 'node:stream';
import { pipeline } from 'node:stream/promises';

const failure = message => Object.assign(new Error(message), { kind: 'download' });

/** 校验可信发布元数据和完整下载内容后，才把临时文件发布为可安装文件。 */
export async function downloadInstaller(url, destination, {
  expectedSize, expectedDigest, onProgress, signal, fetchImpl = fetch,
} = {}) {
  const digest = /^sha256:([a-f0-9]{64})$/i.exec(String(expectedDigest ?? ''))?.[1].toLowerCase();
  if (!digest) throw failure('发布资产缺少 SHA-256 校验值，请前往发布页手动下载。');
  if (!Number.isSafeInteger(expectedSize) || expectedSize <= 0) throw failure('发布资产大小无效。');
  signal?.throwIfAborted();
  await mkdir(path.dirname(destination), { recursive: true });
  const partial = `${destination}.part`;
  let response;
  let committed = false;
  let received = 0;
  const hash = createHash('sha256');
  try {
    response = await fetchImpl(url, { headers: { 'user-agent': 'RenpyBox-NewUI' }, signal });
    if (!response.ok) throw failure(`GitHub 返回 ${response.status}`);
    if (!response.body) throw failure('服务器未返回安装包内容。');
    const length = response.headers.get('content-length');
    if (length !== null && (!/^\d+$/.test(length) || Number(length) !== expectedSize)) {
      throw failure('下载响应长度与发布资产大小不一致。');
    }
    const counter = new Transform({
      transform(chunk, _encoding, callback) {
        received += chunk.length;
        if (received > expectedSize) return callback(failure('下载内容超过发布资产大小。'));
        hash.update(chunk);
        onProgress?.({ received, total: expectedSize });
        callback(null, chunk);
      },
    });
    await pipeline(Readable.fromWeb(response.body), counter, createWriteStream(partial), { signal });
    signal?.throwIfAborted();
    if (received !== expectedSize) throw failure('下载未完成，文件大小与发布资产不一致。');
    if (hash.digest('hex') !== digest) throw failure('SHA-256 校验失败，安装包已丢弃，请重试。');
    await rename(partial, destination);
    committed = true;
    signal?.throwIfAborted();
    return { path: destination, size: received, total: expectedSize };
  } catch (error) {
    if (response?.body && !response.body.locked) await response.body.cancel().catch(() => {});
    await rm(partial, { force: true }).catch(() => {});
    if (committed) await rm(destination, { force: true }).catch(() => {});
    if (error?.name === 'AbortError' || error?.kind) throw error;
    throw Object.assign(failure(error?.message || '下载或写入文件失败'), { cause: error });
  }
}
