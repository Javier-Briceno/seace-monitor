import express from 'express';
import { authMiddleware } from './middleware/auth.js';
import { seaceRouter } from './routes/seace.js';

const app = express();
const PORT = process.env.PORT || 3000;

app.use(express.json())

app.get('/health', (req, res) => {
  res.json({status: true, timestamp: new Date().toISOString()})
})

app.use('/seace', authMiddleware, seaceRouter);

app.get('/myip', async (req, res) => {
  const response = await fetch('https://api.ipify.org?format=json');
  const data = await response.json();
  res.json(data);
});

app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`)
});