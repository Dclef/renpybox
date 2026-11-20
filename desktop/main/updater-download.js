import { createHash } from 'node:crypto';
import { createReadStream, createWriteStream } from 'node:fs';
import { mkdir, rename, rm, stat } from 'node:fs/promises';
import path from 'node:path';
import { Readable, Transform } from 'node:stream';
import { pipeline } from 'node:stream/promises';

/** kind 决定界面文案，retryable 决定上层是「换镜像重试」还是直接放弃。 */
const failure = (message, retryable = true) => Object.assign(new Error(message), { kind: 'download', retryable });

/** 内容与发布元数据对不上：文件必须丢弃，重试也没用。 */
const integrityFailure = message => Object.assign(failure(message, false), { integrity: true });

const CONTENT_RANGE = /^bytes\s+(\d+)-(\d+)\/(\d+|\*)$/i;

function parseContentRange(value) {
  const match = CONTENT_RANGE.exec(String(value ?? '').trim());
  if (!match) return null;
  return {
    start: Number(match[1]),
    end: Number(match[2]),
    total: match[3] === '*' ? null : Number(match[3]),
  };
}

/** 流式校验磁盘上已有文件的 SHA-256；大小或哈希对不上返回 false。 */
async function verifiedFile(file, expectedSize, digest) {
  const info = await stat(file).catch(() => null);
  if (!info?.isFile() || info.size !== expectedSize) return false;
  const hash = createHash('sha256');
  try {
    for await (const chunk of createReadStream(file)) hash.update(chunk);
  } catch {
    return false;
  }
  return hash.digest('hex') === digest;
}

/**
 * 校验可信发布元数据和完整下载内容后，才把临时文件发布为可安装文件。
 *
 * 下载中断（网络断开或用户取消）时保留 .part：下次调用带 Range 续传，
 * 只补剩下的字节，并把已有前缀流式喂进 SHA-256 后继续计算。
 * 只有内容与元数据对不上（长度、哈希）时才丢弃 .part 与目标文件。
 */
export async function downloadInstaller(url, destination, {
  expectedSize, expectedDigest, onProgress, signal, fetchImpl = fetch,
} = {}) {
  const digest = /^sha256:([a-f0-9]{64})$/i.exec(String(expectedDigest ?? ''))?.[1].toLowerCase();
  if (!digest) throw failure('发布资产缺少 SHA-256 校验值，请前往发布页手动下载。', false);
  if (!Number.isSafeInteger(expectedSize) || expectedSize <= 0) throw failure('发布资产大小无效。', false);
  signal?.throwIfAborted();
  await mkdir(path.dirname(destination), { recursive: true });

  // 已经下好并校验通过的安装包不必再发一次几百 MB 的请求。
  if (await verifiedFile(destination, expectedSize, digest)) {
    return { path: destination, size: expectedSize, total: expectedSize };
  }
  await rm(destination, { force: true }).catch(() => {});

  const partial = `${destination}.part`;
  let offset = 0;
  const leftover = await stat(partial).catch(() => null);
  if (leftover?.isFile()) {
    if (leftover.size > expectedSize) {
      // 比发布资产还大，只能认为这份半成品是坏的。
      await rm(partial, { force: true }).catch(() => {});
    } else if (leftover.size === expectedSize) {
      // 上次其实已经下满（可能在改名之前被打断），校验通过就直接发布。
      if (await verifiedFile(partial, expectedSize, digest)) {
        signal?.throwIfAborted();
        await rename(partial, destination);
        return { path: destination, size: expectedSize, total: expectedSize };
      }
      await rm(partial, { force: true }).catch(() => {});
    } else {
      offset = leftover.size;
    }
  }

  let hash = createHash('sha256');
  if (offset > 0) {
    // 先喂完整的前缀再把 append 写流打开，避免读写同一文件竞争。
    try {
      for await (const chunk of createReadStream(partial)) hash.update(chunk);
    } catch (error) {
      await rm(partial, { force: true }).catch(() => {});
      throw Object.assign(failure(error?.message || '读取已下载内容失败'), { cause: error });
    }
  }

  const requestHeaders = { 'user-agent': 'RenpyBox' };
  if (offset > 0) requestHeaders.range = `bytes=${offset}-`;

  let response;
  let received = offset;
  try {
    response = await fetchImpl(url, { headers: requestHeaders, signal });
    if (response.status === 416) {
      // 服务器认为区间越界：丢掉半截文件，下一轮自然从零开始。
      if (response.body && !response.body.locked) await response.body.cancel().catch(() => {});
      await rm(partial, { force: true }).catch(() => {});
      throw failure('GitHub 返回 416');
    }
    if (!response.ok) throw failure(`GitHub 返回 ${response.status}`, false);
    if (!response.body) throw failure('服务器未返回安装包内容。', false);

    let append = false;
    if (response.status === 206) {
      const range = parseContentRange(response.headers.get('content-range'));
      if (!range || range.start !== offset || range.total !== expectedSize) {
        throw failure('服务器返回的续传区间与已下载进度不一致。');
      }
      append = offset > 0;
    } else {
      // 服务器忽略了 Range（200）：原来的半截文件作废，从零重下。
      if (offset > 0) {
        offset = 0;
        received = 0;
        hash = createHash('sha256');
      }
      const length = response.headers.get('content-length');
      if (length !== null && (!/^\d+$/.test(length) || Number(length) !== expectedSize)) {
        throw failure('下载响应长度与发布资产大小不一致。', false);
      }
    }

    const counter = new Transform({
      transform(chunk, _encoding, callback) {
        received += chunk.length;
        if (received > expectedSize) return callback(integrityFailure('下载内容超过发布资产大小。'));
        hash.update(chunk);
        onProgress?.({ received, total: expectedSize });
        callback(null, chunk);
      },
    });
    await pipeline(
      Readable.fromWeb(response.body),
      counter,
      createWriteStream(partial, { flags: append ? 'a' : 'w' }),
      { signal },
    );

    if (received !== expectedSize) throw integrityFailure('下载未完成，文件大小与发布资产不一致。');
    if (hash.digest('hex') !== digest) throw integrityFailure('SHA-256 校验失败，安装包已丢弃，请重试。');
    // 到这里内容已经完整且校验通过：取消也不必丢弃，下次直接把 .part 改名即可。
    signal?.throwIfAborted();
    await rename(partial, destination);
    return { path: destination, size: received, total: expectedSize };
  } catch (error) {
    if (response?.body && !response.body.locked) await response.body.cancel().catch(() => {});
    if (error?.integrity) {
      await rm(partial, { force: true }).catch(() => {});
      await rm(destination, { force: true }).catch(() => {});
    }
    if (error?.name === 'AbortError' || error?.kind) throw error;
    // 网络中断、连接被重置：保留 .part，下次带 Range 接着下。
    throw Object.assign(failure(error?.message || '下载或写入文件失败'), { cause: error });
  }
}
