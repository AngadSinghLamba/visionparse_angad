# app.py  ── VisionParse 4.1  ------------------------------------------------
# Upload PDF / DOCX / XLSX → Markdown + assets → ZIP download
# Adds toggles and instrumentation: EasyOCR, table/image extract, max pages
# ----------------------------------------------------------------------------

import streamlit as st
import warnings, zipfile, base64, time
from pathlib import Path
from dataclasses import dataclass, field
from typing import List
import io as _io
import pandas as pd
from docx import Document as DocxDocument
from docling.datamodel.base_models import DocumentStream
from docling_core.types.doc import ImageRefMode
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions, TableFormerMode, EasyOcrOptions
)
from docling.document_converter import (
    DocumentConverter, PdfFormatOption, WordFormatOption
)
from docling.pipeline.standard_pdf_pipeline import StandardPdfPipeline
from docling.pipeline.simple_pipeline      import SimplePipeline
from docling.backend.pypdfium2_backend      import PyPdfiumDocumentBackend
from docling.datamodel.base_models          import InputFormat

warnings.filterwarnings("ignore", message="'pin_memory' argument is set as true but not supported on MPS")

# ────────────────────────────────────────────────────────────────────────
# 1. CONFIG
# ────────────────────────────────────────────────────────────────────────
@dataclass
class VisionParseConfig:
    SUPPORTED_TYPES: List[str] = field(default_factory=lambda: ["pdf", "docx", "xlsx"])
    DEFAULT_IMAGE_SCALE: float    = 3.0
    OUTPUT_DIR: Path              = Path("artifacts")

# ────────────────────────────────────────────────────────────────────────
# 2. SESSION STATE
# ────────────────────────────────────────────────────────────────────────
def init_session():
    st.session_state.setdefault("files", [])

# ────────────────────────────────────────────────────────────────────────
# 3. DOCLING CONVERTER (EasyOCR for PDF; Word via simple pipeline)
# ────────────────────────────────────────────────────────────────────────
@st.cache_resource(show_spinner="🔧 Loading Docling & EasyOCR…")
def get_converter(easy_ocr: bool, extract_images: bool, extract_tables: bool, image_scale: float):
    pdf_opts = PdfPipelineOptions(
        do_ocr=easy_ocr,
        ocr_options=EasyOcrOptions(force_full_page_ocr=True, lang=["en"]) if easy_ocr else None,
        do_table_structure=extract_tables,
        table_structure_options=dict(mode=TableFormerMode.ACCURATE, do_cell_matching=False) if extract_tables else None,
        generate_page_images=extract_images,
        generate_picture_images=extract_images,
        images_scale=image_scale,
    )
    return DocumentConverter(
        allowed_formats=[InputFormat.PDF, InputFormat.DOCX],
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_cls=StandardPdfPipeline,
                backend=PyPdfiumDocumentBackend,
                pipeline_options=pdf_opts
            ),
            InputFormat.DOCX: WordFormatOption(pipeline_cls=SimplePipeline)
        }
    )

# ────────────────────────────────────────────────────────────────────────
# 4. HELPERS
# ────────────────────────────────────────────────────────────────────────
def make_download_link(buf: bytes, name="visionparse_output.zip"):
    b64 = base64.b64encode(buf).decode()
    return f'<a href="data:application/zip;base64,{b64}" download="{name}">⬇️ Download ZIP</a>'

def export_pdf_tables(doc, md_path: Path, zf: zipfile.ZipFile):
    try:
        for i, tbl in enumerate(doc.iter_tables(), 1):
            csv_p = md_path.parent / f"{md_path.stem}_table_{i}.csv"
            tbl.to_csv(csv_p)
            zf.write(csv_p, csv_p.relative_to(md_path.parent.parent).as_posix())
    except Exception:
        pass

def export_docx_assets(data: bytes, base: Path, extract_images: bool, extract_tables: bool):
    imgs, tbls = [], []
    doc = DocxDocument(_io.BytesIO(data))
    if extract_images:
        for i, rel in enumerate(doc.part._rels.values(), start=1):
            if "image" in rel.target_ref:
                blob = rel.target_part.blob
                p = base / f"{base.stem}_image_{i}.png"
                p.write_bytes(blob)
                imgs.append(p)
    if extract_tables:
        for j, table in enumerate(doc.tables, start=1):
            rows = [[cell.text for cell in row.cells] for row in table.rows]
            df   = pd.DataFrame(rows)
            p    = base / f"{base.stem}_table_{j}.csv"
            df.to_csv(p, index=False)
            tbls.append(p)
    return imgs, tbls

# ────────────────────────────────────────────────────────────────────────
# 5. STREAMLIT APP
# ────────────────────────────────────────────────────────────────────────
def main():
    cfg = VisionParseConfig()
    st.set_page_config("VisionParse 4.1", "📄", "wide")
    st.title("📄 VisionParse 4.1 – PDF / Word / Excel → Markdown + Assets")

    init_session()

    # Sidebar controls
    easy_ocr       = st.sidebar.checkbox("Enable EasyOCR (PDF)", value=True)
    extract_tables = st.sidebar.checkbox("Extract Tables", value=True)
    extract_images = st.sidebar.checkbox("Extract Images", value=True)
    image_scale    = st.sidebar.slider("Image Resolution Scale", 1.0, 4.0, cfg.DEFAULT_IMAGE_SCALE, 0.5)
    max_pages      = st.sidebar.number_input("Max pages (PDF)", 1, 500, 10)

    files = st.file_uploader(
        "Upload PDF, Word (.docx), or Excel (.xlsx)",
        type=cfg.SUPPORTED_TYPES,
        accept_multiple_files=True
    )
    if files:
        st.session_state.files = files

    if st.button("🚀 Convert All", disabled=not st.session_state.files):
        converter = get_converter(easy_ocr, extract_images, extract_tables, image_scale)
        out_root  = cfg.OUTPUT_DIR
        out_root.mkdir(exist_ok=True)

        zip_buf = _io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in st.session_state.files:
                name = Path(f.name).stem
                ext  = Path(f.name).suffix.lower().strip(".")
                data = f.read()
                base = out_root / name
                base.mkdir(exist_ok=True)

                # ── EXCEL (.xlsx) ───────────────────────────────────
                if ext == "xlsx":
                    if extract_tables:
                        sheets = pd.read_excel(_io.BytesIO(data), sheet_name=None)
                        for sheet, df in sheets.items():
                            csv_p = base / f"{name}_{sheet}_table.csv"
                            df.to_csv(csv_p, index=False)
                            zf.write(csv_p, csv_p.relative_to(out_root).as_posix())

                            md_txt = df.to_markdown(index=False)
                            md_p   = base / f"{name}_{sheet}.md"
                            md_p.write_text(md_txt, encoding="utf-8")
                            zf.write(md_p, md_p.relative_to(out_root).as_posix())

                    continue  # done with Excel

                # ── WORD (.docx) ───────────────────────────────────
                if ext == "docx":
                    imgs, tbls = export_docx_assets(data, base, extract_images, extract_tables)

                    # parse text via Docling
                    src = DocumentStream(name=f.name, stream=_io.BytesIO(data))
                    res = converter.convert(src, max_num_pages=max_pages)

                    md_p = base / f"{name}.md"
                    res.document.save_as_markdown(md_p, image_mode=ImageRefMode.REFERENCED)

                    zf.write(md_p, md_p.relative_to(out_root).as_posix())
                    for img in imgs: zf.write(img, img.relative_to(out_root).as_posix())
                    for tbl in tbls: zf.write(tbl, tbl.relative_to(out_root).as_posix())

                    continue

                # ── PDF (.pdf) ─────────────────────────────────────
                src = DocumentStream(name=f.name, stream=_io.BytesIO(data))
                t0  = time.time()
                try:
                    res = converter.convert(src, max_num_pages=max_pages)
                except Exception as e:
                    st.error(f"Error converting {f.name}: {e}")
                    continue
                st.sidebar.write(f"{f.name} → {time.time()-t0:.1f}s")

                md_p = base / f"{name}.md"
                res.document.save_as_markdown(
                    md_p,
                    image_mode=(ImageRefMode.REFERENCED if extract_images else "text")
                )
                zf.write(md_p, md_p.relative_to(out_root).as_posix())

                if extract_tables:
                    export_pdf_tables(res.document, md_p, zf)
                if extract_images:
                    for img in base.glob("*.png"):
                        zf.write(img, img.relative_to(out_root).as_posix())

        st.success("✅ All done!")
        st.markdown(make_download_link(zip_buf.getvalue()), unsafe_allow_html=True)

    if st.button("🗑️ Clear session"):
        st.session_state.files.clear()
        st.experimental_rerun()

if __name__ == "__main__":
    main()
