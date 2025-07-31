# Conversational RAG Q&A System

This is a sophisticated, full-stack Retrieval-Augmented Generation (RAG) system designed to answer questions from a variety of document types, including PDFs, PPTX, and spreadsheets (CSV/XLSX). It features a decoupled architecture with a FastAPI backend and a Streamlit frontend, making it scalable and ready for deployment.

## Features

*   **Multi-Modal Data Ingestion:** Processes text from PDFs and PPTs, and structured data from CSV and XLSX files.
*   **Intelligent Query Handling:** Automatically classifies user queries as text-based, SQL-based, or hybrid, and routes them to the appropriate retrieval pipeline.
*   **Advanced Contextual Understanding:** Utilizes a dual vector store architecture:
    *   A **global vector store** for answering general questions from all text documents.
    *   **Local vector stores** for each project folder, providing specific context for spreadsheet analysis.
*   **Powered by Google Gemini:** Leverages the Google Gemini API for all language model tasks, from generating SQL queries to synthesizing natural language answers.
*   **Decoupled Architecture:** A robust FastAPI backend handles all data processing and RAG logic, while a user-friendly Streamlit application provides the interface.

## Architecture

The application is composed of two main components:

1.  **Backend (FastAPI):** An API server that exposes endpoints for processing documents and answering queries. It contains all the core logic for the RAG pipeline.
2.  **Frontend (Streamlit):** A web-based user interface that allows users to interact with the system. It communicates with the backend via HTTP requests.

## Setup and Installation

1.  **Clone the repository:**
    ```bash
    git clone <repository_url>
    cd <repository_name>
    ```

2.  **Install dependencies:**
    It is recommended to use a virtual environment.
    ```bash
    python -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    ```

3.  **Set up your API Key:**
    You need a Google Gemini API key. You can set it as an environment variable:
    ```bash
    export GEMINI_API_KEY="your_api_key_here"
    ```
    Alternatively, you can add it to a `.env` file in the root of the project:
    ```
    GEMINI_API_KEY="your_api_key_here"
    ```

## How to Run

1.  **Start the Backend API:**
    Open a terminal and run the following command from the root of the project:
    ```bash
    uvicorn api:app --reload
    ```
    The API will be available at `http://127.0.0.1:8000`.

2.  **Start the Frontend Application:**
    Open a second terminal and run the following command:
    ```bash
    streamlit run app.py
    ```
    The Streamlit application will be available at `http://localhost:8501` (or another URL printed to the console).

## How to Use

1.  **Add Your Data:**
    *   Place your documents in project-specific subfolders inside the `/data` directory. For example:
        ```
        /data
        ├── /project_one
        │   ├── report.pdf
        │   └── data.csv
        └── /project_two
            ├── analysis.pptx
            └── numbers.xlsx
        ```

2.  **Process Documents:**
    *   Open the Streamlit application in your browser.
    *   In the sidebar, click the "Process Documents" button.
    *   The status will change to "processing". Wait for it to become "complete".

3.  **Ask Questions:**
    *   Once processing is complete, use the chat interface to ask questions about your documents.

## Project Structure

```
.
├── api.py              # FastAPI backend server
├── app.py              # Streamlit frontend application
├── requirements.txt    # Project dependencies
├── data/               # Directory for your project folders and documents
│   ├── project_alpha/
│   └── project_beta/
└── src/                # Source code for the RAG pipeline
    ├── __init__.py
    ├── config.py
    ├── file_extractor.py
    ├── llm_gemini.py
    ├── rag_pipeline.py
    ├── sql_database.py
    ├── text_processing.py
    ├── utils.py
    └── vector_store.py
```
