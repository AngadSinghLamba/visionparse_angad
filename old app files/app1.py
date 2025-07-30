# app.py ── VisionParse w/ .txt in ZIP -----------------------------
import streamlit as st
import warnings, zipfile, base64, io, json, yaml, tempfile, os
from pathlib import Path
from dataclasses import dataclass, field
from typing import List

import pandas as pd

from docling.datamodel.base_models import DocumentStream, InputFormat
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions,
    TableFormerMode,
    EasyOcrOptions,
    TableStructureOptions
)
from docling.document_converter import (
    DocumentConverter,
    PdfFormatOption,
    WordFormatOption
)
from docling.pipeline.standard_pdf_pipeline import StandardPdfPipeline
from docling.pipeline.simple_pipeline import SimplePipeline
from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
from docling.utils.export import generate_multimodal_pages
from docling_core.types.doc import ImageRefMode, TableItem, PictureItem

warnings.filterwarnings("ignore", message="'pin_memory' argument is set as true but not supported on MPS")

# ────────────────────────────────────────────────────────────
@dataclass
class VisionParseConfig:
    SUPPORTED_EXTS: List[str] = field(default_factory=lambda: [
        "pdf","docx","xlsx","html","htm","pptx","md","csv",
        "png","jpg","jpeg","asciidoc"
    ])
    DEFAULT_IMAGE_SCALE: float = 2.0
    MAX_FILE_SIZE: int = 20_971_520  # 20MB
    OUTPUT_DIR: Path = Path("artifacts")

def init_session():
    st.session_state.setdefault("files", [])

@st.cache_resource(show_spinner="🔧 Loading Docling & OCR…")
def get_converter(use_ocr: bool, extract_tables: bool, extract_images: bool, image_scale: float):
    pdf_opts = PdfPipelineOptions(
        do_ocr=use_ocr,
        ocr_options=EasyOcrOptions(force_full_page_ocr=True, lang=["en"]) if use_ocr else None,
        do_table_structure=extract_tables,
        generate_page_images=extract_images,
        generate_picture_images=extract_images,
        images_scale=image_scale,
    )
    if extract_tables:
        pdf_opts.table_structure_options = TableStructureOptions(
            mode=TableFormerMode.ACCURATE,
            do_cell_matching=True
        )

    return DocumentConverter(
        allowed_formats=[
            InputFormat.PDF,InputFormat.DOCX,InputFormat.XLSX,
            InputFormat.HTML,InputFormat.MD,InputFormat.CSV,
            InputFormat.IMAGE,InputFormat.PPTX,InputFormat.ASCIIDOC
        ],
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_cls=StandardPdfPipeline,
                backend=PyPdfiumDocumentBackend,
                pipeline_options=pdf_opts
            ),
            InputFormat.DOCX: WordFormatOption(pipeline_cls=SimplePipeline),
            InputFormat.HTML: WordFormatOption(),
            InputFormat.CSV:  WordFormatOption(),
            InputFormat.XLSX: WordFormatOption(),
            InputFormat.PPTX: WordFormatOption(),
        }
    )

def export_tables(doc, base: Path, extract_tables: bool):
    if extract_tables and hasattr(doc, "tables"):
        for i, tbl in enumerate(doc.tables, start=1):
            df = tbl.export_to_dataframe()
            p  = base / f"{base.name}_table_{i}.csv"
            df.to_csv(p, index=False)

def generate_txt(res, base: Path):
    lines, ti, pi = [], 0, 0
    imgs = sorted(base.glob("*.png"))
    for el, _ in res.document.iterate_items():
        lvl = getattr(el, "level", None)
        txt = getattr(el, "text", "").strip()
        if isinstance(lvl, int) and txt:
            lines.append(f"{'#'*lvl} {txt}")
        elif isinstance(el, TableItem):
            ti += 1
            df = el.export_to_dataframe()
            lines.append(f"[Table {ti}]")
            lines.append(df.to_string(index=False))
        elif isinstance(el, PictureItem):
            fn = imgs[pi].name if pi < len(imgs) else f"{base.name}_img_{pi+1}.png"
            pi += 1
            lines.append(f"[Image: {fn}]")
        elif txt:
            lines.append(txt)
    txt_file = base / f"{base.name}.txt"
    txt_file.write_text("\n\n".join(lines), encoding="utf-8")
    return txt_file

# ────────────────────────────────────────────────────────────
def main():
    cfg = VisionParseConfig()
    st.set_page_config("VisionParse", "📄", "wide")
    st.title("📄 VisionParse – Bulk AI Document Parser")

    init_session()

    # Sidebar toggles
    use_ocr        = st.sidebar.checkbox("Enable OCR (PDF)", True)
    extract_tables = st.sidebar.checkbox("Extract Tables", False)
    extract_images = st.sidebar.checkbox("Extract Images", False)
    export_mm      = st.sidebar.checkbox("Export Multimodal Parquet", False)
    image_scale    = st.sidebar.slider("Image Scale (PDF)", 1.0, 4.0, cfg.DEFAULT_IMAGE_SCALE, 0.5)
    max_pages      = st.sidebar.number_input("Max Pages (PDF)", 1, 500, 100)

    files = st.file_uploader(
        "Upload files (PDF, Word, Excel, HTML, Markdown, CSV, Images…)",
        type=cfg.SUPPORTED_EXTS,
        accept_multiple_files=True
    )
    if files:
        st.session_state.files = files

    if st.button("🚀 Convert All", disabled=not st.session_state.files):
        converter = get_converter(use_ocr, extract_tables, extract_images, image_scale)
        out_root  = cfg.OUTPUT_DIR
        out_root.mkdir(exist_ok=True)

        total   = len(st.session_state.files)
        progress= st.progress(0)
        status  = st.empty()
        results = []

        for idx, f in enumerate(st.session_state.files, start=1):
            status.text(f"Processing {f.name} ({idx}/{total})…")
            ext  = Path(f.name).suffix.lower().lstrip(".")
            base = out_root / Path(f.name).stem
            base.mkdir(exist_ok=True)

            # Excel via pandas
            if ext == "xlsx":
                if extract_tables:
                    sheets = pd.read_excel(io.BytesIO(f.read()), sheet_name=None)
                    for sh, df in sheets.items():
                        pfx = f"{base.name}_{sh}"
                        (base/f"{pfx}.csv").write_text(df.to_csv(index=False), encoding="utf-8")
                        (base/f"{pfx}.md" ).write_text(df.to_markdown(index=False), encoding="utf-8")
                        (base/f"{pfx}.html").write_text(df.to_html(index=False), encoding="utf-8")
                        (base/f"{pfx}.txt").write_text(df.to_string(index=False), encoding="utf-8")
                progress.progress(idx/total)
                continue

            # PDF → tmp file → convert_all → next(gen)
            if ext == "pdf":
                data = f.read()
                tmp  = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
                tmp.write(data); tmp.flush(); tmp.close()
                try:
                    gen = converter.convert_all(
                        [tmp.name],
                        max_num_pages=max_pages,
                        max_file_size=cfg.MAX_FILE_SIZE,
                        raises_on_error=False
                    )
                    res = next(gen)
                finally:
                    os.unlink(tmp.name)
            else:
                src = DocumentStream(name=f.name, stream=io.BytesIO(f.read()))
                gen = converter.convert_all(
                    [src],
                    max_num_pages=max_pages,
                    max_file_size=cfg.MAX_FILE_SIZE,
                    raises_on_error=False
                )
                res = next(gen)

            # Export MD/HTML/JSON/TXT/Tables
            (base / f"{base.name}.md"  ).write_text(res.document.export_to_markdown(image_mode=ImageRefMode.REFERENCED), encoding="utf-8")
            (base / f"{base.name}.html").write_text(res.document.export_to_html(   image_mode=ImageRefMode.REFERENCED), encoding="utf-8")
            (base / f"{base.name}.json").write_text(json.dumps(res.document.export_to_dict(), ensure_ascii=False), encoding="utf-8")
            generate_txt(res, base)
            export_tables(res.document, base, extract_tables)

            results.append(res)
            progress.progress(idx/total)

        status.text("Finalizing…")

        # Optionally export multimodal parquet
        if export_mm:
            rows=[]
            for res in results:
                for text, md, dt, cells, segs, page in generate_multimodal_pages(res):
                    img = page.image
                    rows.append({
                        "doc": res.input.file.name,
                        "page": page.page_no,
                        "text": text,
                        "markdown": md,
                        "doctag": dt,
                        "cells": cells,
                        "segments": segs,
                        "img_w": img.width  if img else None,
                        "img_h": img.height if img else None,
                        "img_bytes": img.tobytes() if img else None
                    })
            df = pd.json_normalize(rows)
            buf= io.BytesIO(); df.to_parquet(buf, index=False); buf.seek(0)
            st.download_button("⬇️ Download Parquet",
                data=buf.getvalue(), file_name="visionparse_multimodal.parquet",
                mime="application/octet-stream"
            )

        # ─── Package EVERYTHING into the ZIP, including .txt ─────────
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for docdir in out_root.iterdir():
                if not docdir.is_dir():
                    continue
                for file in docdir.rglob("*"):
                    if file.is_file():
                        arcname = file.relative_to(out_root).as_posix()
                        zf.write(file, arcname)
        zip_buf.seek(0)

        st.success("✅ All done!")
        st.download_button("⬇️ Download ZIP",
            data=zip_buf.getvalue(),
            file_name="visionparse_output.zip",
            mime="application/zip"
        )

        status.empty()
        progress.empty()

    if st.button("🗑️ Clear Session"):
        st.session_state.files.clear()
        st.experimental_rerun()

if __name__ == "__main__":
    main()
