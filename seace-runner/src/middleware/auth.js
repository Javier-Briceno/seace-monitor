const SEACE_AUTH_TOKEN = process.env.SEACE_AUTH_TOKEN || "";

if(!SEACE_AUTH_TOKEN) throw new Error("SEACE_AUTH_TOKEN must be defined");

export function authMiddleware(req, res, next) {
  // AUTH TOKEN is not necessary on dev mode
  if (!SEACE_AUTH_TOKEN) return next();

  const header = req.headers.authorization || "";
  if (header === `Bearer ${SEACE_AUTH_TOKEN}`) { return next() }

  return res.status(401).json({ error: "Unauthorized" });
}