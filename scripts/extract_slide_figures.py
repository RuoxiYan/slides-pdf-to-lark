#!/usr/bin/env python3
"""Local PDF figure candidates, native assets and review crops. No cloud writes.
Requires PyMuPDF >= 1.24. Run --help. Candidate detection is heuristic, not approval.
"""
import argparse, hashlib, html, json, math
from pathlib import Path
import pymupdf as fitz


def box(r):
    return [round(v, 3) for v in r]


def expand(r, n):
    return fitz.Rect(r.x0-n, r.y0-n, r.x1+n, r.y1+n)


def area(r):
    return max(0,r.width)*max(0,r.height)


def overlap(a,b):
    return area(a & b) / max(1, min(area(a),area(b)))


def groups(rects, gap=3):
    # Connected regions, excluding slide borders/backgrounds upstream.
    result=[]
    for r in rects:
        r=fitz.Rect(r)
        while True:
            hits=[i for i,s in enumerate(result) if expand(r,gap).intersects(s)]
            if not hits: break
            for i in reversed(hits): r |= result.pop(i)
        result.append(r)
    return result


def slide_regions(page, drawings):
    candidates=[]
    for d in drawings:
        r=d['rect']; frac=area(r)/area(page.rect)
        # Broad landscape-frame heuristic. Exposed in manifest; visually verify.
        if r.height>60 and 0.045<frac<0.90 and 1.2<r.width/r.height<2.2:
            if d.get('fill') == (1.0,1.0,1.0) and any(i[0]=='re' for i in d['items']):
                candidates.append(r)
    candidates.sort(key=area,reverse=True)
    found=[]
    for r in candidates:
        if not any(overlap(r,s)>.85 for s in found): found.append(r)
    if len(found)<2: return [page.rect], 'whole_page_fallback'
    return sorted(found,key=lambda r:(round(r.y0/15),r.x0)), 'landscape_frame_heuristic'


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('pdf',type=Path); ap.add_argument('--out',required=True,type=Path)
    ap.add_argument('--pages',help='1-based comma-separated pages, default all')
    ap.add_argument('--regions',type=Path,help='JSON: slides and/or figures, each with page, bbox in unrotated PDF points; optional title/after_text')
    ap.add_argument('--dpi',type=int,default=220)
    args=ap.parse_args()
    if not 72<=args.dpi<=600: ap.error('dpi must be 72..600')
    if args.out.exists(): ap.error('output directory already exists; use a new directory')
    custom=json.loads(args.regions.read_text()) if args.regions else {}
    doc=fitz.open(args.pdf)
    pages=sorted(set(int(x) for x in args.pages.split(','))) if args.pages else list(range(1,len(doc)+1))
    if any(n<1 or n>len(doc) for n in pages): ap.error('page out of range')
    for kind in ('slides','figures'):
        for entry in custom.get(kind,[]):
            r=fitz.Rect(entry['bbox']); n=entry['page']
            if n<1 or n>len(doc) or r.is_empty or not all(math.isfinite(v) for v in r): ap.error('invalid custom region')
            p=doc[n-1]; pr=p.rect * p.derotation_matrix
            if not pr.contains(r): ap.error('custom bbox outside page')
    args.out.mkdir(parents=True); assets=args.out/'assets';assets.mkdir()
    manifest={'source':str(args.pdf.resolve()),'sha256':hashlib.sha256(args.pdf.read_bytes()).hexdigest(),
              'coordinate_system':'unrotated PDF points, top-left origin; pages 1-based',
              'review_status':'pending','pages':[],'figures':[]}
    cache={}; gallery=[]
    for n in pages:
        p=doc[n-1]; original_rotation=p.rotation; p.set_rotation(0)
        drawings=p.get_drawings(); images=p.get_image_info(xrefs=True)
        configured=[fitz.Rect(x['bbox']) for x in custom.get('slides',[]) if x['page']==n]
        slides,method=(configured,'configured') if configured else slide_regions(p,drawings)
        texts=[{'bbox':box(b[:4]),'text':b[4].strip()} for b in p.get_text('blocks') if b[6]==0 and b[4].strip()]
        inventory=[]
        for im in images:
            r=fitz.Rect(im['bbox']);inventory.append({'xref':im['xref'],'bbox':box(r),'pixels':[im['width'],im['height']],
                'candidate_size':r.width>=20 and r.height>=15})
        record={'page':n,'original_rotation':original_rotation,'slide_detection':method,'slides':[box(r) for r in slides],
                'image_occurrences':inventory,'texts':texts}
        manifest['pages'].append(record)
        candidates=[]
        manual=[x for x in custom.get('figures',[]) if x['page']==n]
        for si,sr in enumerate(slides,1):
            ir=[fitz.Rect(x['bbox']) for x in images if sr.contains(fitz.Rect(x['bbox'])) and fitz.Rect(x['bbox']).width>=20 and fitz.Rect(x['bbox']).height>=15]
            vr=[]
            for d in drawings:
                r=d['rect']
                if not sr.contains(r) or area(r)>.65*area(sr): continue
                if r.width>.8*sr.width and r.height<5:continue
                if r.y0<sr.y0+sr.height*.13:continue
                vr.append(expand(r,.1))
            for r in groups(ir+vr):
                if r.width<20 or r.height<15 or area(r)>.70*area(sr):continue
                candidates.append({'bbox':box(expand(r,.7)&sr),'slide_position':si,'method':'automatic_region'})
        if manual:
            candidates=[]
            for x in manual:
                r=fitz.Rect(x['bbox']);si=next((i for i,s in enumerate(slides,1) if s.contains(r)),None)
                candidates.append(dict(x,slide_position=si,method='configured_region'))
        annotated=fitz.open();annotated.insert_pdf(doc,from_page=n-1,to_page=n-1);apage=annotated[0];apage.set_rotation(0)
        for index,c in enumerate(candidates,1):
            r=fitz.Rect(c['bbox'])&p.rect; ident=f'p{n:03}-f{index:03}'
            raw=[];warnings=[]
            for im in images:
                ib=fitz.Rect(im['bbox']);xref=im['xref']
                if not expand(r,.02).contains(ib) or ib.width<20 or ib.height<15:continue
                if not xref:
                    warnings.append('inline image: composite crop used');continue
                if xref not in cache:
                    try:
                        meta=doc.extract_image(xref);smask=meta.get('smask',0)
                        if smask:
                            pix=fitz.Pixmap(doc,xref);mask=fitz.Pixmap(doc,smask)
                            if pix.alpha:pix=fitz.Pixmap(pix,0)
                            pix=fitz.Pixmap(pix,mask)
                            if pix.colorspace and pix.colorspace.n not in (1,3):pix=fitz.Pixmap(fitz.csRGB,pix)
                            filename=f'assets/xref-{xref}.png';pix.save(args.out/filename)
                        else:
                            filename=f'assets/xref-{xref}.{meta["ext"]}';(args.out/filename).write_bytes(meta['image'])
                        cache[xref]=filename
                    except Exception as exc:
                        warnings.append(f'native extraction failed for {xref}: {type(exc).__name__}');continue
                raw.append({'xref':xref,'file':cache[xref],'bbox':box(ib)})
            crop=f'assets/{ident}.png';p.get_pixmap(clip=r,dpi=args.dpi,alpha=False).save(args.out/crop)
            nearby=sorted(texts,key=lambda t:abs(fitz.Rect(t['bbox']).y1-r.y0)+abs(fitz.Rect(t['bbox']).x0-r.x0)*.2)[:3]
            figure={'id':ident,'page':n,**c,'bbox':box(r),'crop':crop,'native_images':raw,
                    'nearby_text':nearby,'warnings':warnings,'review_status':'pending'}
            manifest['figures'].append(figure)
            apage.draw_rect(r,color=(1,0,0),width=1);apage.insert_text((r.x0,max(10,r.y0-2)),str(index),fontsize=9,color=(1,0,0))
            gallery.append(f'<article><h3>{ident} · slide position {c["slide_position"]}</h3><img src="{crop}"><p>原生图片对象：{len(raw)}；待核验</p></article>')
        preview=f'page-{n:03}-locations.png';apage.get_pixmap(dpi=100,alpha=False).save(args.out/preview);annotated.close()
        record['preview']=preview
        print(f'page {n}: {len(slides)} slide regions; {len(images)} image occurrences; {len(candidates)} figure candidates',flush=True)
    (args.out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    intro=''.join(f'<details><summary>PDF {x["page"]} 位置核对</summary><img src="{x["preview"]}"></details>' for x in manifest['pages'])
    (args.out/'review.html').write_text('<!doctype html><meta charset="utf-8"><title>课件图片提取核对</title><style>body{font-family:system-ui;margin:30px;background:#f5f5f5}main{display:grid;grid-template-columns:repeat(2,1fr);gap:20px}article{background:white;padding:18px}img{max-width:100%;max-height:700px}p{color:#555}</style><h1>课件图片提取核对</h1><p>自动候选并非最终教学图表。逐图核对完整性与对应文字后，再用于飞书转录。</p>'+intro+'<main>'+''.join(gallery)+'</main>')
    print(f'{len(manifest["figures"])} candidates. Review: {args.out/"review.html"}')

if __name__=='__main__': main()
