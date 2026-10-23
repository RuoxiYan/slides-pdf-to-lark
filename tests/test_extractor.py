"""Integration checks using generated shapes only; no private lecture files."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
import pymupdf as fitz

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'extract_slide_figures.py'

class ExtractorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.pdf = self.root / 'sample.pdf'
        doc = fitz.open()
        p = doc.new_page(width=600, height=400)
        # Transparent native asset, repeated on the same page.
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 60, 40), True)
        pix.clear_with(0)
        for y in range(5, 35):
            for x in range(5, 55):
                pix.set_pixel(x, y, (30, 100, 200, 180))
        xref = p.insert_image(fitz.Rect(40, 70, 160, 150), stream=pix.tobytes('png'))
        p.insert_image(fitz.Rect(240, 70, 360, 150), xref=xref)
        p.draw_rect(fitz.Rect(60, 220, 200, 320), color=(0, 0, 0))
        p.draw_line((65, 310), (190, 235), color=(0, 0, 1))
        p.insert_text((50, 40), 'Synthetic example')
        doc.save(self.pdf)
        doc.close()

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), str(self.pdf), *map(str,args)], capture_output=True, text=True)

    def test_native_reuse_mask_and_vector_candidates(self):
        out = self.root / 'figures'
        result = self.run_cli('--out', out)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads((out/'manifest.json').read_text())
        self.assertEqual(len(data['pages']), 1)
        self.assertEqual(len(data['figures']), 3)
        natives = [a for f in data['figures'] for a in f['native_images']]
        self.assertEqual(len(natives), 2)
        self.assertEqual(natives[0]['file'], natives[1]['file'])
        self.assertTrue(fitz.Pixmap(str(out/natives[0]['file'])).alpha)
        self.assertTrue(any(not f['native_images'] for f in data['figures']))
        for f in data['figures']:
            self.assertTrue((out/f['crop']).is_file())
            self.assertEqual(f['review_status'], 'pending')
        self.assertTrue((out/'review.html').is_file())
        self.assertNotEqual(self.run_cli('--out',out).returncode, 0)

    def test_explicit_region_and_metadata(self):
        config = self.root/'regions.json'
        config.write_text(json.dumps({'figures':[{'page':1,'bbox':[40,70,160,150],'after_text':'Example paragraph'}]}))
        out=self.root/'manual'
        result=self.run_cli('--out',out,'--regions',config)
        self.assertEqual(result.returncode,0,result.stderr)
        figures=json.loads((out/'manifest.json').read_text())['figures']
        self.assertEqual(len(figures),1)
        self.assertEqual(figures[0]['after_text'],'Example paragraph')
        self.assertEqual(figures[0]['bbox'],[40,70,160,150])

    def test_invalid_page_leaves_no_output(self):
        out=self.root/'invalid'
        self.assertNotEqual(self.run_cli('--out',out,'--pages','2').returncode,0)
        self.assertFalse(out.exists())

    def test_invalid_bbox_leaves_no_output(self):
        out=self.root/'invalid'
        config=self.root/'invalid.json'
        config.write_text(json.dumps({'figures':[{'page':1,'bbox':[-10,0,80,80]}]}))
        self.assertNotEqual(self.run_cli('--out',out,'--regions',config).returncode,0)
        self.assertFalse(out.exists())

if __name__ == '__main__':
    unittest.main()
