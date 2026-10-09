import { createContext, useContext } from 'react';
import { zh } from './zh';
import { en } from './en';

export type Lang = 'ZH' | 'EN';
export type TextKey = keyof typeof zh;

export function normalizeLang(value: unknown): Lang {
  return value === 'EN' ? 'EN' : 'ZH';
}

export function createT(lang: Lang): (key: TextKey) => string {
  const table: Record<TextKey, string> = lang === 'EN' ? en : zh;
  return (key) => table[key] ?? zh[key];
}

export const I18nContext = createContext<(key: TextKey) => string>(createT('ZH'));
export const useT = () => useContext(I18nContext);
