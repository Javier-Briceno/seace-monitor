import { Router } from 'express';
import fs from 'fs';
import path from 'path';
import { PDFDocument } from 'pdf-lib';

export const pdfRouter = Router();

// POST /pdf/base64
// Returns the PDF content in base64 along with size and page metadata.
// n8n uses pageCount and fileSizeMB to decide whether to send it directly to Claude
// or to the pdf-extractor microservice.
// Body: { filePath: "downloads/uuid_bases.pdf" }

pdfRouter.post('/base64', async (req, res) => {
    try {
        const { filePath } = req.body;

        if (!filePath) {
            return res.status(400).json({ error: 'filePath is required' });
        }

        if (!filePath.startsWith('downloads/')) {
            return res.status(403).json({ error: 'Access denied' });
        }

        const absolutePath = path.resolve('/app', filePath);

        if (!absolutePath.startsWith(path.resolve('/app', 'downloads/'))) {
            return res.status(403).json({ error: 'Access denied' });
        }

        if (!fs.existsSync(absolutePath)) {
            return res.status(404).json({ error: `File not found: ${filePath}` })
        }

        const fileBuffer = fs.readFileSync(absolutePath);
        const fileSizeMB = parseFloat((fileBuffer.length / (1024 * 1024)).toFixed(2));
        const base64 = fileBuffer.toString('base64');

        // Try to get pageCount using pdf-lib.  
        // If the PDF is corrupted or encrypted, pageCount remains null,
        // and n8n treats it as "unknown" -> routing to the extractor for safety.
        let pageCount = null;
        try {
            const pdfDoc = await PDFDocument.load(fileBuffer, {
                ignoreEncryption: true,
            });
            pageCount = pdfDoc.getPageCount();
        } catch (_) {
            // pageCount null -> n8n routes to pdf-extractor
        }
        res.json({ 
            base64, 
            mimeType: 'application/pdf',
            filePath,
            fileSizeMB,
            pageCount,
            exceedsClaudeLimit: fileSizeMB > 22 || pageCount > 100 || pageCount === null 
        });
    
    } catch(e) {
        res.status(500).json({error: e.message})
    }
});