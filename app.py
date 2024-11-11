import streamlit as st
import base64
import json
import yaml
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import (
    DocumentConverter, 
    PdfFormatOption, 
    WordFormatOption
)
from docling.datamodel.base_models import DocumentStream, InputFormat
from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
from docling.pipeline.simple_pipeline import SimplePipeline
from docling.pipeline.standard_pdf_pipeline import StandardPdfPipeline

@dataclass
class AppConfig:
    SUPPORTED_TYPES: Dict[str, List[str]] = field(default_factory=lambda: {
        "PDF": ["pdf"],
        "Word Document": ["docx"],
        "HTML": ["html", "htm"],
        "PowerPoint": ["pptx"],
        "Image": ["png", "jpg", "jpeg"],
        "AsciiDoc": ["asciidoc"],
        "Markdown": ["md"],
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
    if isinstance(content, (dict, list)):  # For JSON/YAML content
        content = json.dumps(content) if file_name.endswith('.json') else yaml.safe_dump(content)
    
    if isinstance(content, str):
        content = content.encode()
        
    b64 = base64.b64encode(content).decode()
    href = f'<a href="data:application/octet-stream;base64,{b64}" download="{file_name}">{file_label}</a>'
    return href

class DocumentConverterUI:
    def __init__(self, config: AppConfig):
        self.config = config
        
    def setup_page(self):
        st.set_page_config(
            page_title="Enhanced Document Converter",
            page_icon="🔗",
            layout="wide",
            initial_sidebar_state="expanded",
        )
        
        st.title("🔗 Docling Converter")
        st.markdown("Convert documents with extended output options")
        st.markdown("Follow Me on [Github](https://github.com/hparreao)")
    
    def render_main_content(self) -> dict:
        tab1, tab2 = st.tabs(["Upload", "Advanced Settings"])
        
        with tab1:
            # File Upload Section
            st.header("File Upload")
            file_type = st.selectbox(
                'Select file type',
                list(self.config.SUPPORTED_TYPES.keys())
            )
            
            uploaded_file = st.file_uploader(
                f'Upload {file_type} file',
                type=self.config.SUPPORTED_TYPES[file_type]
            )
            
            if uploaded_file:
                st.session_state.current_file = uploaded_file
            
            # Output Format Selection
            output_format = st.radio(
                "Output Format",
                options=self.config.OUTPUT_FORMATS,
                horizontal=True
            )
            
            col1, col2 = st.columns(2)
            with col1:
                start_conversion = st.button(
                    'Start Conversion',
                    disabled=st.session_state.current_file is None,
                    use_container_width=True
                )
            
            with col2:
                if st.button('Clear', use_container_width=True):
                    st.session_state.current_file = None
                    st.session_state.conversion_result = None
                    st.rerun()
        
        with tab2:
            st.header("Advanced Settings")
            use_ocr = st.checkbox("Enable OCR", value=True)
            
            # Show image resolution only for PDFs and images
            image_resolution = self.config.DEFAULT_IMAGE_SCALE
            if (st.session_state.current_file and 
                (file_type == "PDF" or file_type == "Image")):
                image_resolution = st.slider(
                    "Image Resolution Scale",
                    1.0, 4.0, 2.0, 0.5
                )
        
        return {
            'file_type': file_type,
            'use_ocr': use_ocr,
            'image_resolution': image_resolution,
            'output_format': output_format,
            'start_conversion': start_conversion
        }

class DocumentProcessor:
    @staticmethod
    @st.cache_resource
    def get_converter(use_ocr: bool = True) -> DocumentConverter:
        pipeline_options = PdfPipelineOptions(
            do_ocr=use_ocr,
            do_table_structure=False
        )

        return DocumentConverter(
            allowed_formats=[
                InputFormat.PDF,
                InputFormat.IMAGE,
                InputFormat.DOCX,
                InputFormat.HTML,
                InputFormat.PPTX,
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

    @staticmethod
    def process_document(file, settings: dict, config: AppConfig):
        try:
            converter = DocumentProcessor.get_converter(
                use_ocr=settings['use_ocr']
            )
            
            file_content = file.read()
            buf = BytesIO(file_content)
            source = DocumentStream(name=file.name, stream=buf)
            
            with st.spinner(f"Converting {file.name}..."):
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
    
    # Process output based on selected format
    if settings['output_format'] == "Markdown":
        output_content = result.document.export_to_markdown()
        output_filename = f"{base_filename}.md"
    elif settings['output_format'] == "JSON":
        output_content = result.document.export_to_dict()
        output_filename = f"{base_filename}.json"
    else:  # YAML
        output_content = result.document.export_to_dict()
        output_filename = f"{base_filename}.yaml"

    # Display success message and download link
    st.success("Conversion completed successfully!")
    st.markdown(
        get_binary_file_downloader_html(
            output_content,
            output_filename,
            f"Download {settings['output_format']} File"
        ),
        unsafe_allow_html=True
    )

    # Preview the converted content
    st.subheader("Preview")
    if isinstance(output_content, (dict, list)):
        if settings['output_format'] == "JSON":
            st.json(output_content)
        else:  # YAML
            st.code(yaml.safe_dump(output_content), language="yaml")
    else:
        st.markdown(output_content)

def main():
    config = AppConfig()
    ui = DocumentConverterUI(config)
    
    # Setup page
    ui.setup_page()
    
    # Initialize session state
    initialize_session_state()
    
    # Render main content and get settings
    settings = ui.render_main_content()
    
    # Process document if Start Conversion is clicked
    if settings['start_conversion'] and st.session_state.current_file:
        result = DocumentProcessor.process_document(
            st.session_state.current_file, 
            settings, 
            config
        )
        handle_conversion_output(result, settings, st.session_state.current_file)

if __name__ == '__main__':
    main()