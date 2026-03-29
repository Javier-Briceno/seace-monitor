import { Router } from 'express';
import fs from 'fs';
import path from 'path';
import { execSync } from 'child_process';
import mammoth from 'mammoth';
import AdmZip from 'adm-zip';

export const documentRouter = Router();

const DOWNLOADS_PREFIX  = 'downloads/';
const APP_ROOT = '/app';

// Validates that the filePath is safe (inside downloads/).
// Prevents path traversal.
function resolveFilePath(filePath) {
    if (!filePath || !filePath.startsWith(DOWNLOADS_PREFIX)) {
        return null;
    }
    const abs = path.resolve(APP_ROOT, filePath);
    const allowed = path.resolve(APP_ROOT, DOWNLOADS_PREFIX);
    // Ensure that the resolved path still stays within downloads/
    if (!abs.startsWith(allowed)) return null;
    return abs;
}

// POST /document/text
// Extracts plain text from a DOCX file.
// Body: { filePath: "downloads/uuid_bases.docx" }
documentRouter.post('/text', async (req, res) => {
    try {
        const {filePath} = req.body;
        if (!filePath) return res.status(400).json({ error: 'filePath is required' });
        
        const absPath = resolveFilePath(filePath);
        if (!absPath) return res.status(403).json({ error: 'Access denied' });

        if (!fs.existsSync(absPath)) {
            return res.status(404).json({ error: `File not found: ${filePath}` });
        }

        const ext = path.extname(filePath).toLowerCase();
        if (ext !== '.docx') {
            return res.status(400).json({ error: `Expected .docx, got ${ext}` });
        }

        const result = await mammoth.extractRawText({ path: absPath });
        
        // Warnings from mammoth (e.g. unsupported formatting) — these are not fatal errors
        const warnings = result.messages
            .filter(m => m.type === 'warning')
            .map(m => m.message);
        
        res.json({
            text: result.value,
            charCount: result.value.length,
            filePath,
            warnings: warnings.length > 0 ? warnings : undefined,
        });

    } catch (e) {
        res.status(500).json({ error: e.message });
    }
});

// POST /document/extract-archive
// Extracts the contents of a ZIP or RAR file and returns the list of files.
// Only extracts if the file is a ZIP or RAR. Files are extracted to downloads/extracted_<uuid>/.
// Body: { filePath: "downloads/uuid_bases.zip" }
documentRouter.post('/extract-archive', async(req, res) => {
    try {
        const { filePath } = req.body;
        if (!filePath) return res.status(400).json({ error: 'filePath is required' });

        const absPath = resolveFilePath(filePath);
        if (!absPath) return res.status(403).json({ error: 'Access denied' });

        if (!fs.existsSync(absPath)) {
            return res.status(404).json({ error: `File not found: ${filePath}` });
        }

        const ext = path.extname(filePath).toLowerCase();
        if (ext !== '.zip' && ext !== '.rar') {
            return res.status(400).json({ error: `Expected .zip or .rar, got ${ext}` });
        }

        // Extraction folder with unique name
        const extractDirName = `extracted_${Date.now()}`;
        const extractDir = path.join(APP_ROOT, DOWNLOADS_PREFIX, extractDirName);
        fs.mkdirSync(extractDir, { recursive: true });

        if (ext === '.zip') {
            const zip = new AdmZip(absPath);
            zip.extractAllTo(extractDir, true /* overwrite */)
        } else {
            // RAR: use unar (supports RAR3 and RAR5, available in the container)
            // -o: output directory. -f: overwrite without prompting.
            execSync(`unar -o "${extractDir}" -f "${absPath}"`, {timeout: 60_000});
        }
        
        // Read extracted contents (first level only, non-recursive — SEACE archives
        // rarely contain nested directories)
        const entries = fs.readdirSync(extractDir, { withFileTypes: true });
        const files = entries
            .filter(e => e.isFile())
            .map(e => {
                const relPath = `${DOWNLOADS_PREFIX}${extractDirName}/${e.name}`;
                const absFile = path.join(extractDir, e.name);
                const stats = fs.statSync(absFile);
                return {
                    filename: e.name,
                    local_path: relPath,
                    ext: path.extname(e.name).toLowerCase(),
                    fileSizeMB: parseFloat((stats.size / (1024 * 1024)).toFixed(2)),
                };
            });
        
        res.json({
            files,
            extractDir: `${DOWNLOADS_PREFIX}${extractDirName}`,
            totalFiles: files.length,
            sourceFile: filePath,
        });

    } catch (e) {
        res.status(500).json({ error: e.message });
    }
});