# doclingconverter

A Streamlit web application for converting various document formats using the Docling library.

Streamlit Application: https://doclingconvert.streamlit.app/

## Features

- Convert multiple document formats (PDF, DOCX, HTML, PPTX, Images)
- Multiple output formats (Markdown, JSON, YAML)
- OCR support for scanned documents
- Advanced image resolution settings
- Clean and intuitive interface

## Installation

1. Clone the repository:
```bash
git clone https://github.com/hparreao/doclingconverter.git
cd docling-converter
```

2. Create a virtual environment and install dependencies:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

3. Run the app locally:
```bash
streamlit run app.py
```

## Usage

1. Select the document type from the dropdown
2. Upload your document
3. Choose the desired output format
4. Adjust advanced settings if needed
5. Click "Start Conversion"
6. Download the converted file
