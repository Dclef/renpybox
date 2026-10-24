/**
 * 角色头像。
 *
 * 画布里的头像必须裁成圆形，而三种来源的取景完全不同（faces 是脸部特写、headshots 是头+肩、
 * portraits 是半身），所以按 kind 反算取景窗口，保证「头部大约占圆 60~85%」，不会出现只剩眼睛
 * 看不到下巴的情况。没有立绘时退回「名字首字 + 名字 hash 决定的固定色相」色块。
 */
import { useId, useState } from 'react';

import { apiBase } from '../../api';
import { fallbackColor, firstLetter, type CharacterAvatar } from './relationGraph';

type AvatarInput = Partial<CharacterAvatar> | null | undefined;

/** 图路径：施工单字段是 relative，后端落盘还带一份 relative_path，两个都认。 */
function avatarPath(avatar: AvatarInput): string {
  const relative = String(avatar?.relative ?? avatar?.relative_path ?? '').trim();
  return relative;
}

/** 立绘走校对页已有的资源接口；路径是 game/ 下的相对路径。 */
export function avatarUrl(avatar: AvatarInput): string {
  const relative = avatarPath(avatar);
  if (!relative) return '';
  return `${apiBase()}/api/proofreading/asset?path=${encodeURIComponent(relative)}`;
}

interface FrameConfig { sideByHeight: number; sideWidthRatio: number; top: number }

const FRAMING: Record<string, FrameConfig> = {
  faces: { sideByHeight: 0, sideWidthRatio: 1, top: 0.06 },
  headshots: { sideByHeight: 0.52, sideWidthRatio: 0, top: 0.03 },
  portraits: { sideByHeight: 0.4, sideWidthRatio: 0, top: 0.03 },
};

/** 按来源反算正方形取景框在图片里的位置。 */
export function framingBox(avatar: CharacterAvatar): { x: number; y: number; side: number } {
  const width = Math.max(1, Number(avatar.width) || 0);
  const height = Math.max(1, Number(avatar.height) || 0);
  const config = FRAMING[avatar.kind] ?? FRAMING.portraits;
  const side = Math.max(1, Math.min(width, config.sideByHeight ? height * config.sideByHeight : width * config.sideWidthRatio));
  return { x: (width - side) / 2, y: height * config.top, side };
}

/** 有完整立绘信息才算可用：宽高缺失时画不出正确取景，直接退回色块。 */
export function usableAvatar(avatar: AvatarInput): CharacterAvatar | null {
  if (!avatar) return null;
  const relative = avatarPath(avatar);
  const width = Number(avatar.width) || 0;
  const height = Number(avatar.height) || 0;
  if (!relative || width <= 0 || height <= 0) return null;
  return { kind: String(avatar.kind ?? '') || 'portraits', relative, width, height };
}

interface AvatarCard {
  id: string;
  name: string;
  avatar?: AvatarInput;
}

interface SvgAvatarProps {
  card: AvatarCard;
  cx: number;
  cy: number;
  r: number;
  /** 无立绘时的兜底色：图谱里传关系类别色，色块才不会跟类别撞车。 */
  color?: string;
}

/** SVG 版头像：给画布里的中心角色和圆环节点共用。 */
export function SvgAvatar(props: SvgAvatarProps) {
  const { card, cx, cy, r, color } = props;
  const clipId = useId().replace(/[^a-zA-Z0-9_-]/g, '');
  const [broken, setBroken] = useState(false);
  const avatar = usableAvatar(card.avatar);

  if (!avatar || broken) {
    return (
      <>
        <circle cx={cx} cy={cy} r={r} fill={color || fallbackColor(card)} />
        <text x={cx} y={cy + r * 0.34} textAnchor="middle" fontSize={r * 0.92} fill="#FFFFFF" fontWeight={600}>
          {firstLetter(card)}
        </text>
      </>
    );
  }

  const box = framingBox(avatar);
  const scale = (r * 2) / box.side;
  return (
    <>
      <defs>
        <clipPath id={`rb-graph-clip-${clipId}`}>
          <circle cx={cx} cy={cy} r={r} />
        </clipPath>
      </defs>
      <g clipPath={`url(#rb-graph-clip-${clipId})`}>
        <image
          x={cx - r - box.x * scale}
          y={cy - r - box.y * scale}
          width={avatar.width * scale}
          height={avatar.height * scale}
          href={avatarUrl(avatar)}
          onError={() => setBroken(true)}
        />
      </g>
    </>
  );
}

interface AvatarBlockProps {
  card: AvatarCard;
  size: number;
  className?: string;
}

/** HTML 版头像：给左列名册和右侧详情卡头用。 */
export function AvatarBlock(props: AvatarBlockProps) {
  const { card, size, className } = props;
  const [broken, setBroken] = useState(false);
  const avatar = usableAvatar(card.avatar);
  const style = { width: size, height: size, fontSize: Math.max(11, Math.round(size * 0.38)) };
  if (!avatar || broken) {
    return (
      <span className={`rb-graph-avatar ${className ?? ''}`} style={{ ...style, background: fallbackColor(card) }} aria-hidden>
        {firstLetter(card)}
      </span>
    );
  }
  return (
    <span className={`rb-graph-avatar ${className ?? ''}`} style={style} aria-hidden>
      <img src={avatarUrl(avatar)} alt="" onError={() => setBroken(true)} />
    </span>
  );
}
