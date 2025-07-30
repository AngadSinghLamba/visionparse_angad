# app.py  ── VisionParse with Progress & Download Buttons -------------
import streamlit as st
import warnings, zipfile, base64, io, json, yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import List

import pandas as pd
from docling.datamodel.base_models import DocumentStream, InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, TableFormerMode, EasyOcrOptions
from docling.document_converter import DocumentConverter, PdfFormatOption, WordFormatOption
from docling.pipeline.standard_pdf_pipeline import StandardPdfPipeline
from docling.pipeline.simple_pipeline import SimplePipeline
from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
from docling.utils.export import generate_multimodal_pages
from docling_core.types.doc import ImageRefMode, TableItem, PictureItem

warnings.filterwarnings("ignore", message="'pin_memory' argument is set as true but not supported on MPS")

# ──────────────────────────────────────────────────────────────────────
@dataclass
class VisionParseConfig:
    SUPPORTED_EXTS: List[str] = field(default_factory=lambda: [
        "pdf", "docx", "xlsx", "html", "htm", "pptx", "md", "csv",
        "png", "jpg", "jpeg", "asciidoc"
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
        table_structure_options=dict(mode=TableFormerMode.ACCURATE, do_cell_matching=True) if extract_tables else None,
        generate_page_images=extract_images,
        generate_picture_images=extract_images,
        images_scale=image_scale,
    )
    return DocumentConverter(
        allowed_formats=[
            InputFormat.PDF, InputFormat.DOCX, InputFormat.XLSX,
            InputFormat.HTML, InputFormat.MD, InputFormat.CSV,
            InputFormat.IMAGE, InputFormat.PPTX, InputFormat.ASCIIDOC
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
    paths = []
    if extract_tables and hasattr(doc, "tables"):
        for i, tbl in enumerate(doc.tables, start=1):
            df = tbl.export_to_dataframe()
            p  = base / f"{base.name}_table_{i}.csv"
            df.to_csv(p, index=False)
            paths.append(p)
    return paths

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

# ──────────────────────────────────────────────────────────────────────
def main():
    cfg = VisionParseConfig()
    st.set_page_config("VisionParse", "📄", "wide")
    st.title("📄 VisionParse – Bulk AI Document Parser")

    init_session()

    # Sidebar controls
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

        total = len(st.session_state.files)
        progress = st.progress(0)
        status   = st.empty()

        # Build DocumentStreams
        sources = [
            DocumentStream(name=f.name, stream=io.BytesIO(f.read()))
            for f in st.session_state.files
        ]

        results = list(converter.convert_all(
            sources,
            max_num_pages=max_pages,
            max_file_size=cfg.MAX_FILE_SIZE,
            raises_on_error=False
        ))

        for idx, res in enumerate(results, start=1):
            status.text(f"Processing {res.input.file.name} ({idx}/{total})…")
            name = Path(res.input.file.name).stem
            base = out_root / name
            base.mkdir(exist_ok=True)

            # Markdown
            md_p = base / f"{name}.md"
            res.document.save_as_markdown(md_p, image_mode=ImageRefMode.REFERENCED)
            # HTML
            html_p = base / f"{name}.html"
            res.document.save_as_html(html_p, image_mode=ImageRefMode.REFERENCED)
            # JSON
            json_p = base / f"{name}.json"
            json_p.write_text(json.dumps(res.document.export_to_dict(), ensure_ascii=False), encoding="utf-8")
            # TXT
            generate_txt(res, base)
            # CSV tables & images
            export_tables(res.document, base, extract_tables)

            progress.progress(idx/total)

        status.text("Finalizing…")

        # Multimodal Parquet
        if export_mm:
            rows = []
            for res in results:
                for text, md, dt, cells, segs, page in generate_multimodal_pages(res):
                    rows.append({
                        "doc":       res.input.file.name,
                        "page_no":   page.page_no,
                        "text":      text,
                        "markdown":  md,
                        "doctag":    dt,
                        "cells":     cells,
                        "segments":  segs,
                        "img_w":     page.image.width,
                        "img_h":     page.image.height,
                        "img_bytes": page.image.tobytes(),
                    })
            df = pd.json_normalize(rows)
            buf = io.BytesIO()
            df.to_parquet(buf, index=False)
            buf.seek(0)
            st.download_button(
                "⬇️ Download Multimodal Parquet",
                data=buf.getvalue(),
                file_name="visionparse_multimodal.parquet",
                mime="application/octet-stream"
            )

        # ZIP package
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for doc_dir in out_root.iterdir():
                if not doc_dir.is_dir(): continue
                prefix = doc_dir.name
                for file_path in doc_dir.iterdir():
                    ext = file_path.suffix.lower()
                    if ext == ".md":
                        arc = f"{prefix}/md/{file_path.name}"
                    elif ext == ".html":
                        arc = f"{prefix}/html/{file_path.name}"
                    elif ext == ".json":
                        arc = f"{prefix}/json/{file_path.name}"
                    elif ext == ".txt":
                        arc = f"{prefix}/txt/{file_path.name}"
                    elif ext == ".csv":
                        arc = f"{prefix}/assets/tables/{file_path.name}"
                    elif ext in [".png", ".jpg", ".jpeg"]:
                        arc = f"{prefix}/assets/images/{file_path.name}"
                    else:
                        arc = f"{prefix}/{file_path.name}"
                    zf.write(file_path, arc)
        zip_buf.seek(0)

        st.success("✅ All done!")
        st.download_button(
            "⬇️ Download ZIP of all outputs",
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
