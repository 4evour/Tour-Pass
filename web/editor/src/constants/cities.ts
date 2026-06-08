/**
 * Shared city constants used across the editor.
 * Single source of truth for city emoji mappings and fallback lists.
 */

export const CITY_EMOJI_MAP: Record<string, string> = {
  "武汉": "🌉", "大理": "🏔️", "丽江": "🏘️", "南京": "🏛️", "苏州": "🏡",
  "北京": "🏯", "成都": "🐼", "重庆": "🔥", "杭州": "🌊", "西安": "🏛️",
  "上海": "🌃", "广州": "🌺", "深圳": "💎", "厦门": "🏖️", "青岛": "🍺",
  "桂林": "🏞️", "三亚": "🌊", "哈尔滨": "❄️", "昆明": "🌸", "张家界": "🏔️", "长沙": "🏙️",
};

/** Shared city name list (order matches backend cityList) */
export const CITY_NAMES = Object.keys(CITY_EMOJI_MAP);

/** Fallback for CitiesStep wizard (emoji cards) */
export const WIZARD_FALLBACK_CITIES = CITY_NAMES.map(name => ({
  name,
  emoji: CITY_EMOJI_MAP[name] || '🗺️',
}));

/** Fallback for App city dropdown (select options) */
export const DROPDOWN_FALLBACK_CITIES = CITY_NAMES.map(name => ({
  value: name,
  label: name,
}));
