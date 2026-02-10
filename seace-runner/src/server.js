import express from "express";
import { authMiddleware } from "./middleware/auth.js";
import { seaceRouter } from "./routes/seace.js";

const app = express();
const PORT = process.env.PORT || 3000;

app.use(express.json());

// Health check - no auth required
app.get("/health", (req, res) => {
  res.json({ ok: true, timestamp: new Date().toISOString() });
});

// Test outbound connectivity
app.get("/test-outbound", async (req, res) => {
  try {
    const r = await fetch("https://www.google.com");
    res.json({ ok: true, status: r.status });
  } catch (e) {
    res.status(500).json({ ok: false, error: String(e) });
  }
});

// SEACE routes - auth required
app.use("/seace", authMiddleware, seaceRouter);

app.listen(PORT, () => {
  console.log(`SEACE Runner running on port ${PORT}`);
});