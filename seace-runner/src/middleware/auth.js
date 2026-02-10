const AUTH_TOKEN = process.env.AUTH_TOKEN || "";

/**
 * Bearer token authentication middleware.
 * If AUTH_TOKEN is not set, all requests are allowed (dev mode).
 */
export function authMiddleware(req, res, next) {
  if (!AUTH_TOKEN) return next();

  const header = req.headers.authorization || "";
  if (header === `Bearer ${AUTH_TOKEN}`) return next();

  return res.status(401).json({ error: "Unauthorized" });
}