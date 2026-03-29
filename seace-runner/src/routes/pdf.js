import { Router } from 'express';
import fs from 'fs';

export const pdfRouter = Router();

pdfRouter.post('/base64', async (req, res) => {
    try {
        const { filePath } = req.body;

        if (!filePath) {
            return res.status(400).json({ error: 'filePath is required' });
        }

        if (!filePath.startsWith('downloads/')) {
            return res.status(403).json({ error: 'Access denied' });
        }

        const absolutePath = `/app/${filePath}`;

        if (!fs.existsSync(absolutePath)) {
            return res.status(404).json({ error: `File not found: ${filePath}` })
        }

        const fileBuffer = fs.readFileSync(absolutePath);
        const base64 = fileBuffer.toString('base64');

        res.json({ base64, mimeType: 'application/pdf', filePath });
    
    } catch(e) {
        res.status(500).json({error: e.message})
    }
});