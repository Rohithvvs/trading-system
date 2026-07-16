/**
 * Profile cache — thin re-export of app-wide cache for backward compatibility.
 * All keys share the same memory + sessionStorage store as appCache.
 */

export {
  getCached,
  setCached,
  cachedFetch,
  invalidateCache as invalidateProfileCache,
  PROFILE_CACHE_KEYS,
  CACHE_KEYS,
  getStaleCached,
} from "./appCache";
