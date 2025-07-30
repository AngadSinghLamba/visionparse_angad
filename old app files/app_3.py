import streamlit as st
from pathlib import Path
import tempfile
import logging

from docling.datamodel.base_models import InputFormat
from docling.datamodel.settings import settings
from docling_core.types.doc import ImageRefMode
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions,
    TableFormerMode,
    EasyOcrOptions
)

# Enable built-in profiling flags for pipeline timings
settings.debug.profile_pipeline_timings = True

st.title("PDF to Markdown Converter with Custom Options")

# UI controls for parsing options
ocr_enabled = st.checkbox("OCR", value=True)
table_extraction = st.checkbox("Extract Table Structure", value=True)
image_extraction = st.checkbox("Extract Page & Figure Images", value=True)

# Choose image reference mode
image_mode_option = st.selectbox(
    "Select image mode:",
    options=[ImageRefMode.EMBEDDED, ImageRefMode.REFERENCED],
    format_func=lambda mode: mode.name
)

uploaded_file = st.file_uploader("Upload a PDF file", type=["pdf"])
if uploaded_file:
    st.info("Converting PDF... this may take a moment.")

    # Write uploaded PDF to a temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
        tmp_file.write(uploaded_file.read())
        tmp_path = tmp_file.name

    # Configure pipeline options based on UI
    pipeline_options = PdfPipelineOptions(
        do_ocr=ocr_enabled,
        do_table_structure=table_extraction,
        ocr_options=EasyOcrOptions(force_full_page_ocr=True, lang=["en"]) if ocr_enabled else None,
        table_structure_options=dict(
            do_cell_matching=False,
            mode=TableFormerMode.ACCURATE
        ) if table_extraction else None,
        generate_page_images=image_extraction,
        generate_picture_images=image_extraction,
        images_scale=2.0
    )

    # Initialize converter
    doc_converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
        }
    )

    # Perform conversion
    result = doc_converter.convert(tmp_path)

    # Explain enabled options
    st.write("**Enabled options:**")
    st.write(f"- OCR: {'Yes' if ocr_enabled else 'No'}")
    st.write(f"- Table extraction: {'Yes' if table_extraction else 'No'}")
    st.write(f"- Image extraction: {'Yes' if image_extraction else 'No'}")
    st.write(f"- Image mode: {image_mode_option.name}")

    # Export document as Markdown
    markdown_content = result.document.export_to_markdown(image_mode=image_mode_option)

    # Display rendered Markdown
    st.markdown(markdown_content)

    # Provide download button for the Markdown
    st.download_button(
        label="Download Markdown",
        data=markdown_content,
        file_name=f"{Path(tmp_path).stem}.md",
        mime="text/markdown"
    )
