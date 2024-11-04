import aioboto3
import arxiv
from fastapi import FastAPI, Query, Body, HTTPException
from typing import List
from datetime import datetime, timedelta
from urllib.parse import urlencode
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create a session
session = aioboto3.Session(region_name='us-west-2')

async def get_papers_by_discipline(discipline: str):
    async with session.resource('dynamodb') as dynamo:
        table = await dynamo.Table('arxiv-papers')
        
        response = await table.query(
            IndexName='discipline-date-index',  # Use the GSI
            KeyConditionExpression='discipline = :discipline',
            ExpressionAttributeValues={
                ':discipline': discipline
            }
        )
        
        return response['Items']

@app.get("/papers")
async def read_papers(discipline: str = Query(...)):
    papers = await get_papers_by_discipline(discipline)
    return {"papers": papers}


# Mock function to summarize papers
def generate_summary(discipline: str):
    # This would actually call the LLM API; using mock data here
    return "Summary of recent papers in " + discipline

@app.get("/summarize")
async def summarize(discipline: str = Query(...)):
    summary = generate_summary(discipline)
    return {"summary": summary}


@app.get("/highlights")
async def get_highlights():
    # Mock function for retrieving highlights
    highlights = [{"title": "Highlight Paper", "abstract": "An interesting abstract...", "link": "http://arxiv.org/..."}, ...]
    return {"highlights": highlights}

@app.get("/")
async def root():
    return {
        "message": "Welcome to the ArXiv Summary API",
        "endpoints": {
            "GET /papers": "Get papers by discipline",
            "GET /summarize": "Generate summary for a discipline",
            "GET /highlights": "Get paper highlights"
        }
    }

# Fetch papers from arXiv API
async def fetch_arxiv_papers(max_results: int, categories: List[str]):
    # Construct the arXiv search query
    search_query = " OR ".join(f"cat:{cat}" for cat in categories)
    
    # Use the arxiv library instead of raw API calls
    search = arxiv.Search(
        query=search_query,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.SubmittedDate,
        sort_order=arxiv.SortOrder.Descending
    )
    
    papers = []
    for result in search.results(): 
        paper = {
            "paper_id": result.entry_id.split("/")[-1],
            "date": result.published.strftime("%Y-%m-%d"),
            "discipline": categories[0], # may be arxiv:term, but so far they are always identical
            "title": result.title,
            "summary": result.summary,
            "authors": [author.name for author in result.authors],
            "published": result.published.isoformat(),
            "link": result.pdf_url,
            "categories": result.categories
        }
        papers.append(paper)
    
    return papers

async def store_papers_to_dynamodb(papers: List[dict]):
    async with session.resource('dynamodb') as dynamo:
        table = await dynamo.Table('arxiv-papers')  # Add await here
        
        # Batch write papers to DynamoDB
        async with table.batch_writer() as batch:
            for paper in papers:
                await batch.put_item(Item=paper)

@app.get("/recent")
async def get_recent_papers(
    max_results: int = Query(default=50, le=100),
    categories: List[str] = Query()
):
    papers = await fetch_arxiv_papers(max_results, categories)
    
    if not papers:
        raise HTTPException(status_code=404, detail="No papers found")
        
    await store_papers_to_dynamodb(papers)

    return {"message": f"Successfully stored {len(papers)} papers"}
