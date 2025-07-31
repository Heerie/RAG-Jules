import uvicorn
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
from src.rag_pipeline import RAGPipeline

app = FastAPI()

# This is a simple in-memory store for the RAG pipeline and job status.
# In a production environment, you might use a more robust solution like Redis.
app.state.rag_pipeline = RAGPipeline()
app.state.processing_status = "idle" # idle, processing, complete, error

class QueryRequest(BaseModel):
    query: str
    chat_history: list = []

@app.post("/process")
async def process_documents(background_tasks: BackgroundTasks):
    """
    Starts the document processing pipeline in the background.
    """
    if app.state.processing_status == "processing":
        return {"message": "Processing is already in progress."}

    def process():
        app.state.processing_status = "processing"
        try:
            app.state.rag_pipeline.process_documents()
            app.state.processing_status = "complete"
        except Exception as e:
            app.state.processing_status = f"error: {e}"

    background_tasks.add_task(process)
    return {"message": "Document processing started in the background."}

@app.get("/status")
async def get_status():
    """
    Returns the current status of the document processing job.
    """
    return {"processing_status": app.state.processing_status}

@app.post("/query")
async def query_pipeline(request: QueryRequest):
    """
    Runs a query through the RAG pipeline.
    """
    if app.state.processing_status != "complete":
        return {"answer": "The document processing is not yet complete. Please try again later."}

    try:
        answer = app.state.rag_pipeline.run_query(request.query, request.chat_history)
        return {"answer": answer}
    except Exception as e:
        return {"answer": f"An error occurred: {e}"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
