# Docling Converter 

## Table of Contents

1. Introduction  
2. Features  
3. Quick Start  
4. Installation  
5. Running the Application  
6. Usage Guide  
7. Application Architecture  
8. Programmatic API Reference  
9. Extending the Converter  
10. Deployment  
11. Contributing  
12. License  

---

## 1. Introduction

**Docling Converter** is a [Streamlit](https://streamlit.io/) web application that leverages the powerful **[Docling](https://github.com/axiros/docling)** library to convert a variety of document formats into Markdown, JSON, or YAML. It supports PDF (with optional OCR), Word, HTML, PowerPoint, images, AsciiDoc, and Markdown sources.

The demo is available at: <https://doclingconvert.streamlit.app/>.

---

## 2. Features

• **Multi-format input** – PDF, DOCX, HTML, PPTX, images, AsciiDoc, and Markdown.  
• **Flexible output** – choose between Markdown, JSON, or YAML.  
• **OCR support** – extract text from scanned PDFs/images with one click.  
• **Adjustable image resolution** – fine-tune the DPI multiplier (1.0-4.0).  
• **Streamlit UI** – modern, reactive interface with instant previews & downloads.  

---

## 3. Quick Start

```bash
# clone the repository
$ git clone https://github.com/hparreao/doclingconverter.git
$ cd doclingconverter

# create virtual environment (optional but recommended)
$ python -m venv venv && source venv/bin/activate

# install dependencies
$ pip install -r requirements.txt

# run the Streamlit server
$ streamlit run app.py
```

Navigate to <http://localhost:8501> in your browser and start converting documents.

---

## 4. Installation

The project has only two runtime dependencies:

```text
Docling  # heavy-lifting document conversion engine
Streamlit # frontend/UI framework
```

Both are automatically installed via `requirements.txt`.

For **development** you might also want:

```bash
pip install black isort flake8 pre-commit
```

---

## 5. Running the Application

| Command | Description |
|---------|-------------|
| `streamlit run app.py` | Launch the local development server. |
| `streamlit run app.py --server.headless true` | Run headless (useful for remote/Docker deployments). |

Environment variables (all optional):

| Variable | Purpose | Default |
|----------|---------|---------|
| `DOC_CONVERTER_MAX_PAGES` | Override `AppConfig.MAX_PAGES` | `100` |
| `DOC_CONVERTER_MAX_FILE_SIZE` | Override `AppConfig.MAX_FILE_SIZE` (bytes) | `20971520` |

---

## 6. Usage Guide

1. Select the **document type** from the left sidebar.  
2. **Upload** the file (max 20 MB; max 100 pages).  
3. Pick the desired **output format** (Markdown / JSON / YAML).  
4. Toggle **OCR** and adjust **image resolution** (if available).  
5. Hit **Start Conversion**.  
6. Download the generated file or inspect the preview inline.

---

## 7. Application Architecture

```
app.py        # Streamlit entry-point & main module
│
├── AppConfig                    # Centralised runtime configuration
├── DocumentConverterUI          # UI/UX helpers (layout & widgets)
├── DocumentProcessor            # Wrapper around Docling's DocumentConverter
└── handle_conversion_output()   # Result post-processing & download link
```

The heavy lifting is delegated to `docling.DocumentConverter`. This repository only configures the converter (pipelines, OCR, page limits) and provides a sleek Streamlit interface.

---

## 8. Programmatic API Reference

Below is a high-level overview of the public classes/functions you may import in your own scripts.

### 8.1 `AppConfig`

```python
@dataclass
class AppConfig:
    SUPPORTED_TYPES: Dict[str, List[str]]
    OUTPUT_FORMATS: List[str]
    MAX_PAGES: int
    MAX_FILE_SIZE: int
    DEFAULT_IMAGE_SCALE: float
```

Configuration defaults controlling allowed extensions, limits and UI presets. Feel free to instantiate your own subclass or override attributes at runtime.

### 8.2 `DocumentConverterUI`

Responsible for setting the Streamlit page parameters and rendering the widget tree.

Key methods:

• `setup_page()` – initialises page meta data and header.  
• `render_main_content()` – returns a **settings** dictionary capturing all user-selected options (file type, OCR flag, resolution, etc.).

### 8.3 `DocumentProcessor`

```python
class DocumentProcessor:
    @staticmethod
    @st.cache_resource
    def get_converter(use_ocr: bool = True) -> DocumentConverter: ...

    @staticmethod
    def process_document(file, settings: dict, config: AppConfig): ...
```

1. **`get_converter()`** – creates (and caches) a `docling.DocumentConverter` with customised **pipelines**:
   * PDFs ➜ `StandardPdfPipeline` + `PyPdfiumDocumentBackend`
   * DOCX/HTML/PPTX ➜ `SimplePipeline`

2. **`process_document()`** – orchestrates the conversion, enforces `MAX_PAGES` and `MAX_FILE_SIZE`, and returns a `docling.DocumentConversionResult`.

### 8.4 `handle_conversion_output(result, settings, file)`

Formats the conversion result into the chosen output representation, injects a one-click download link, and renders an inline preview using Streamlit utilities.

---

## 9. Extending the Converter

Want to add new formats or tweak pipelines? Follow these steps:

1. Import the corresponding `InputFormat` and `FormatOption` implementation from **Docling**.
2. Update `DocumentProcessor.get_converter()` by appending a new element to `allowed_formats` and its mapping in `format_options`.
3. (Optional) Extend `AppConfig.SUPPORTED_TYPES` to expose the new extension in the UI dropdown.

Example for adding **EPUB** support:

```python
from docling.datamodel.base_models import InputFormat
from docling.document_converter import EpubFormatOption

# inside get_converter()
allowed_formats=[..., InputFormat.EPUB]
format_options={
    ...,
    InputFormat.EPUB: EpubFormatOption(),
}
```

---

## 10. Deployment

### Docker (recommended)

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.headless", "true"]
```

Then build & run:

```bash
docker build -t docling-converter .
docker run -p 8501:8501 docling-converter
```

### Streamlit Community Cloud

1. Push your fork to GitHub.  
2. Create a new Streamlit app, select the repo and `app.py` as the entry point.  
3. Add `requirements.txt`.  
4. Deploy – that's all!

---

## 11. Contributing

Pull requests and issues are welcome! Please open a discussion if you plan major changes.

Development guidelines:

```bash
# lint & format
$ black . && isort . && flake8

# run app with hot-reload
$ streamlit run app.py
```

---

## 12. License

This project is licensed under the terms of the **MIT License** – see the `LICENSE` file for details.
