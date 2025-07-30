import streamlit as st
import base64
import json
import yaml
import warnings
from io import BytesIO
from dataclasses import dataclass, field
from typing import Dict, List

# Suppress known torch MPS warning
warnings.filterwarnings("ignore", message="'pin_memory' argument is set as true but not supported on MPS")

# Lazy imports inside cache
@st.cache_resource
def get_converter():
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption, WordFormatOption
    from docling.datamodel.base_models import InputFormat
    from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
    from docling.pipeline.simple_pipeline import SimplePipeline
    from docling.pipeline.standard_pdf_pipeline import StandardPdfPipeline

    pipeline_options = PdfPipelineOptions(do_ocr=True, do_table_structure=False)
    
    return DocumentConverter(
        allowed_formats=[
            InputFormat.PDF,
            InputFormat.IMAGE,
            InputFormat.DOCX,
            InputFormat.HTML,
            InputFormat.PPTX,  # NOTE: PPTX still won't work unless you custom-handle it
            InputFormat.ASCIIDOC,
            InputFormat.MD,
        ],
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_cls=StandardPdfPipeline,
                backend=PyPdfiumDocumentBackend,
                pipeline_options=pipeline_options
            ),
            InputFormat.DOCX: WordFormatOption(
                pipeline_cls=SimplePipeline
            ),
            InputFormat.HTML: WordFormatOption(),
            InputFormat.PPTX: WordFormatOption(),
        }
    )

@dataclass
class VisionParseConfig:
    SUPPORTED_TYPES: Dict[str, List[str]] = field(default_factory=lambda: {
        "PDF": ["pdf"],
        "Word Document": ["docx"],
        "HTML": ["html", "htm"],
        "Image": ["png", "jpg", "jpeg"],
        "AsciiDoc": ["asciidoc"],
        "Markdown": ["md"],
        # "PowerPoint": ["pptx"],  # Remove if you don’t support PPTX yet
    })
    OUTPUT_FORMATS: List[str] = field(default_factory=lambda: ["Markdown", "JSON", "YAML"])
    MAX_PAGES: int = 100
    MAX_FILE_SIZE: int = 20_971_520  # 20MB
    DEFAULT_IMAGE_SCALE: float = 2.0

def initialize_session_state():
    if 'current_file' not in st.session_state:
        st.session_state.current_file = None
    if 'conversion_result' not in st.session_state:
        st.session_state.conversion_result = None

def get_binary_file_downloader_html(content, file_name, file_label="File"):
    if isinstance(content, (dict, list)):
        content = json.dumps(content) if file_name.endswith('.json') else yaml.safe_dump(content)
    if isinstance(content, str):
        content = content.encode()
    b64 = base64.b64encode(content).decode()
    href = f'<a href="data:application/octet-stream;base64,{b64}" download="{file_name}">{file_label}</a>'
    return href

class VisionParseUI:
    def __init__(self, config: VisionParseConfig):
        self.config = config
        
    def setup_page(self):
        st.set_page_config(
            page_title="VisionParse - AI Document Parser",
            page_icon="📄",
            layout="wide",
            initial_sidebar_state="expanded",
        )
        st.title("📄 VisionParse: Intelligent Document Parser")
        st.markdown("*Extract structured insights from PDFs, images, and documents in one click.*")
        st.markdown("Follow Me on [GitHub](https://github.com/angadsinghlamba)")

    def render_main_content(self) -> dict:
        tab1, tab2 = st.tabs(["Upload", "Advanced Settings"])
        with tab1:
            st.header("File Upload")
            file_type = st.selectbox('Select file type', list(self.config.SUPPORTED_TYPES.keys()))
            uploaded_file = st.file_uploader(f'Upload {file_type} file', type=self.config.SUPPORTED_TYPES[file_type])
            if uploaded_file:
                st.session_state.current_file = uploaded_file
            output_format = st.radio("Output Format", options=self.config.OUTPUT_FORMATS, horizontal=True)

            col1, col2 = st.columns(2)
            with col1:
                start_conversion = st.button('Start Conversion', disabled=st.session_state.current_file is None, use_container_width=True)
            with col2:
                if st.button('Clear', use_container_width=True):
                    st.session_state.current_file = None
                    st.session_state.conversion_result = None
                    st.rerun()

        with tab2:
            st.header("Advanced Settings")
            use_ocr = st.checkbox("Enable OCR (Slower for scanned images)", value=True)
            image_resolution = self.config.DEFAULT_IMAGE_SCALE
            if (st.session_state.current_file and file_type in ["PDF", "Image"]):
                image_resolution = st.slider("Image Resolution Scale", 1.0, 4.0, 2.0, 0.5)

        return {
            'file_type': file_type,
            'use_ocr': use_ocr,
            'image_resolution': image_resolution,
            'output_format': output_format,
            'start_conversion': start_conversion
        }

def process_document(converter, file, settings: dict, config: VisionParseConfig):
    try:
        from docling.datamodel.base_models import DocumentStream

        file_content = file.read()
        buf = BytesIO(file_content)
        source = DocumentStream(name=file.name, stream=buf)

        with st.spinner(f"Converting {file.name} with VisionParse..."):
            result = converter.convert(
                source,
                max_num_pages=config.MAX_PAGES,
                max_file_size=config.MAX_FILE_SIZE
            )
        return result

    except Exception as e:
        st.error(f"Error during conversion of {file.name}: {str(e)}")
        return None

def handle_conversion_output(result, settings, file):
    if not result:
        return
    base_filename = file.name.rsplit(".", 1)[0]

    if settings['output_format'] == "Markdown":
        output_content = result.document.export_to_markdown()
        output_filename = f"{base_filename}.md"
    elif settings['output_format'] == "JSON":
        output_content = result.document.export_to_dict()
        output_filename = f"{base_filename}.json"
    else:
        output_content = result.document.export_to_dict()
        output_filename = f"{base_filename}.yaml"

    st.success("VisionParse conversion completed successfully!")
    st.markdown(get_binary_file_downloader_html(output_content, output_filename, f"Download {settings['output_format']} File"), unsafe_allow_html=True)

    st.subheader("Preview")
    if isinstance(output_content, (dict, list)):
        st.json(output_content) if settings['output_format'] == "JSON" else st.code(yaml.safe_dump(output_content), language="yaml")
    else:
        st.markdown(output_content)

def main():
    config = VisionParseConfig()
    ui = VisionParseUI(config)
    ui.setup_page()
    initialize_session_state()
    settings = ui.render_main_content()

    if settings['start_conversion'] and st.session_state.current_file:
        converter = get_converter()
        result = process_document(converter, st.session_state.current_file, settings, config)
        handle_conversion_output(result, settings, st.session_state.current_file)

if __name__ == '__main__':
    main()
