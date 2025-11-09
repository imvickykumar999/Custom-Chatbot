import json
import threading
import asyncio
import os
# --- ASYNC/SYNC Bridge Import ---
from asgiref.sync import sync_to_async
# Import the necessary model from the local models.py file
from .models import ScrapedDataEntry 
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.shortcuts import render
from crawl4ai import AsyncWebCrawler
from bs4 import BeautifulSoup
from pydantic import BaseModel, HttpUrl, Field
from typing import Optional

# Store status for each user (this could be moved to a database if persistence is required)
scraping_status = {}

#####################################################################################

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from .models import ScrapedDataEntry

# Core RAG dependencies
import faiss
import numpy as np
import os
import json
from sentence_transformers import SentenceTransformer
from groq import Groq

# --- Initialize Global Resources ---
# Load the embedding model and Groq client once globally to reuse resources.
try:
    # Adjust this path if your model is not cached/downloaded correctly
    model = SentenceTransformer("all-MiniLM-L6-v2")
    print("SentenceTransformer model loaded successfully.")
except Exception as e:
    print(f"Error loading SentenceTransformer model: {e}")
    model = None

# Initialize Groq client using environment variable
GROQ_API_KEY = os.getenv("GROQ_API_KEY") or getattr(settings, 'GROQ_API_KEY', None)

if not GROQ_API_KEY:
    print("Warning: GROQ_API_KEY not found. API functions will likely fail.")
    client = None
else:
    try:
        client = Groq(api_key=GROQ_API_KEY)
        print("Groq client initialized.")
    except Exception as e:
        print(f"Error initializing Groq client: {e}")
        client = None

# --- Helper Functions ---

def get_document_options_from_db():
    """
    Fetches unique content summaries (documents) from the ScrapedDataEntry model.
    """
    # Exclude entries that are null or empty
    entries = ScrapedDataEntry.objects.exclude(content_summary__isnull=True).exclude(content_summary__exact='').values_list('content_summary', flat=True)
    
    # Return a list of unique document strings
    return list(set(entries))

# def get_document_options_from_db(user_id):
#     """
#     Fetches unique content summaries (documents) from the ScrapedDataEntry model,
#     FILTERED by the user who scraped the data.
#     """
#     # Exclude entries that are null or empty AND filter by scraped_by_user_id
#     entries = ScrapedDataEntry.objects.filter(
#         scraped_by_user_id=user_id
#     ).exclude(
#         content_summary__isnull=True
#     ).exclude(
#         content_summary__exact=''
#     ).values_list('content_summary', flat=True)
    
#     # Return a list of unique document strings
#     return list(set(entries))

def find_best_match(question, documents):
    """
    Encodes the question and documents, and finds the document with the highest
    semantic similarity (lowest L2 distance) using FAISS.
    """
    if not model:
        raise RuntimeError("Embedding model failed to load. Cannot perform vector search.")

    all_texts = [question] + documents
    embeddings = model.encode(all_texts)
    embeddings = np.array(embeddings).astype('float32')

    # Separate query and document embeddings
    query_embedding = np.array([embeddings[0]]).astype('float32')
    document_embeddings = embeddings[1:]

    # FAISS Index for Similarity Search (Flat L2 distance is fast and reliable)
    dimension = document_embeddings.shape[1]
    index = faiss.IndexFlatL2(dimension)
    index.add(document_embeddings)

    # Search for the nearest neighbor (k=1)
    # The L2 index returns distance and index
    distances, indices = index.search(query_embedding, 1)
    
    # The index returned is relative to the documents list (embeddings[1:])
    best_match_index = indices[0][0]
    best_match_document = documents[best_match_index]

    return best_match_document

def generate_reply(message_text):
    """
    Uses Groq's Llama 3.1 8B Instant model to generate a concise reply
    based on the best-matched document content (RAG).
    """
    if client is None:
        return "API Key Missing: Cannot generate reply without GROQ_API_KEY."

    try:
        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": "You are a concise blog summarizer. Respond only to the user's prompt based on the provided text, keeping the reply under 50 words."},
                {"role": "user", "content": message_text}
            ],
            temperature=0.7,
            max_tokens=100,
            stream=False,
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        print(f"Groq API Error: {e}")
        return f"Sorry, an API error occurred during generation: {str(e)}"

# --- Django View for API Endpoint ---

@csrf_exempt
def api_search(request):
    """Handles the API request for vector search and Groq generation."""
    if request.method != 'POST':
        return JsonResponse({"error": "Method not allowed"}, status=405)
    
    try:
        # Django parses JSON payload via request.body
        data = json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON format"}, status=400)
        
    question = data.get('question', '').strip()
    # user_id = str(request.user.id) 

    if not question:
        return JsonResponse({"error": "Question field is required"}, status=400)

    try:
        # 1. Get documents from the model
        # document_options = get_document_options_from_db(user_id)
        document_options = get_document_options_from_db()
        
        if not document_options:
            return JsonResponse({"error": "No scraped data found in the database to search against."}, status=503)

        # 2. Find the most relevant document (semantic search)
        best_match_content = find_best_match(question, document_options)
        
        # 3. Use the relevant content to generate a Groq reply (RAG)
        prompt = (
            f'User Question: "{question}" \n\n '
            f'Based on the following relevant content, write a helpful and short reply (under 50 words): \n\n '
            f'Content: "{best_match_content}"'
        )
        # prompt = generate_reply(prompt)
        
        # Return results as JSON
        # Note: 'graph_url' is explicitly removed.
        return JsonResponse({
            "answer": prompt,
            "question": question,
            "matched_content_preview": best_match_content[:50] + "..."
        })
            
    except RuntimeError as e:
        # Catches errors like model not loading
        return JsonResponse({"error": str(e)}, status=500)
    except Exception as e:
        print(f"Error during API processing: {e}")
        return JsonResponse({"error": f"An internal server error occurred: {str(e)}"}, status=500)

########################################################################################


# Define the ScrapedData model using Pydantic for structured data
class ScrapedData(BaseModel):
    name: Optional[str] = Field(None, title="H1 Tag Content")
    meta_title: Optional[str] = Field(None, title="Meta Title")
    meta_description: Optional[str] = Field(None, title="Meta Description")
    meta_keywords: Optional[str] = Field(None, title="Meta Keywords")
    url: HttpUrl
    content: str
    Learn_More: str

    class Config:
        json_encoders = {HttpUrl: str}

# ----------------------------------------------------
# --- URL Normalization Utility ---
# ----------------------------------------------------
def normalize_url(url: str) -> str:
    """
    Removes a trailing slash if present, unless the URL is the root (e.g., https://example.com/).
    This prevents duplicates like '/about' and '/about/'.
    """
    if url.endswith('/') and url.strip('/') != "":
        return url.rstrip('/')
    return url

# ----------------------------------------------------
# --- Database Helper Functions (Async-Safe ORM) ---
# ----------------------------------------------------

@sync_to_async
def check_url_exists(url):
    """Checks if the normalized URL exists in the database."""
    normalized_url = normalize_url(url)
    return ScrapedDataEntry.objects.filter(url=normalized_url).exists()

@sync_to_async
def save_scraped_data_to_db_sync(scraped_data, user_id, scrape_mode):
    """
    Saves data using the normalized URL string.
    """
    # Normalize the URL before saving
    normalized_url_str = normalize_url(str(scraped_data['url']))
    
    # Save new entry
    ScrapedDataEntry.objects.create(
        url=normalized_url_str, # SAVING THE NORMALIZED URL
        scraped_by_user_id=user_id,
        scrape_mode=scrape_mode,
        name=scraped_data.get('name'),
        meta_title=scraped_data.get('meta_title'),
        meta_description=scraped_data.get('meta_description'),
        meta_keywords=scraped_data.get('meta_keywords'),
        content_summary=scraped_data.get('content', '')
    )
    print(f"Successfully saved new entry for: {normalized_url_str}")
    return True

async def save_scraped_data_wrapper(scraped_data, user_id, scrape_mode, status):
    """
    Asynchronous wrapper to handle error logging and the duplicate check before saving.
    """
    url_to_check = str(scraped_data['url'])
    
    try:
        # Check for duplication again before saving (using normalized URL check)
        if await check_url_exists(url_to_check):
             print(f"Skipping save for duplicate URL: {url_to_check}")
             status["error"] = f"Skipped duplicate URL: {url_to_check}"
             return False
             
        await save_scraped_data_to_db_sync(scraped_data, user_id, scrape_mode)
        return True

    except Exception as e:
        print(f"Error saving data to database: {e}")
        status["error"] = f"Error saving data to database: {str(e)}"
        return False
# ----------------------------------------------------

# Asynchronous function to get URLs from a sitemap
async def get_sitemap_urls(sitemap_url):
    import aiohttp
    async with aiohttp.ClientSession() as session:
        async with session.get(sitemap_url) as response:
            sitemap_xml = await response.text()
    soup = BeautifulSoup(sitemap_xml, "xml")
    urls = [loc.get_text(strip=True) for loc in soup.find_all("loc")]
    return urls

# Function to remove unnecessary tags like headers, footers, and sidebars
def remove_header_footer(soup):
    for tag in soup.find_all(["header", "footer", "nav"]):
        tag.decompose()
    for tag in soup.find_all(class_=lambda x: x and ("cookie" in x.lower() or "sidebar" in x.lower())):
        tag.decompose()
    for p in soup.find_all("p"):
        if "cookie" in p.get_text().lower():
            p.decompose()

# Process a URL to extract content and metadata
async def process_url(crawler, url, status):
    # Check for duplication early before expensive scraping. Uses the normalization function.
    if await check_url_exists(url):
        print(f"Skipping scrape for existing URL: {url}")
        status["error"] = f"Skipped scrape for existing URL: {url}"
        status["rem_link"] = status.get("rem_link", 0) - 1
        return None

    try:
        print(f"Starting to scrape {url}")
        status["current_url"] = url
        result = await crawler.arun(url=url)
        html_content = getattr(result, 'html', result.markdown)
        soup = BeautifulSoup(html_content, "html.parser")

        h1_tag = soup.find('h1')
        h1_value = h1_tag.get_text(strip=True) if h1_tag else None

        remove_header_footer(soup)

        title_tag = soup.find('title')
        meta_title = title_tag.get_text(strip=True) if title_tag else None

        meta_desc_tag = soup.find('meta', attrs={'name': 'description'})
        meta_description = (meta_desc_tag['content'].strip() if meta_desc_tag and meta_desc_tag.has_attr('content') else None)

        meta_keywords_tag = soup.find('meta', attrs={'name': 'keywords'})
        meta_keywords = (meta_keywords_tag['content'].strip() if meta_keywords_tag and meta_keywords_tag.has_attr('content') else None)

        content = soup.get_text(separator="\n", strip=True)
        char_count = len(content)
        
        # Update total characters directly in the status object
        status["total_characters_scraped"] += char_count

        # Create a ScrapedData object and return it
        scraped_data = ScrapedData(
            name=h1_value,
            meta_title=meta_title,
            meta_description=meta_description,
            meta_keywords=meta_keywords,
            url=result.url,
            Learn_More=f"{h1_value} - For more info, go to {result.url}",
            content=content
        )

        status["rem_link"] = status.get("rem_link", 0) - 1
        return scraped_data.dict() # Return the scraped data dictionary
    except Exception as e:
        print(f"Error processing {url}: {e}")
        status["error"] = f"Error processing {url}: {str(e)}"
        return None

# Function to scrape a single page
async def scrape_single_page_with_status(page_url, status):
    if status.get("rem_link", 0) <= 0:
        status["is_scraping"] = False
        status["error"] = "Your current plan doesn’t support fetching data from this URL — consider upgrading your plan."
        return

    status["is_scraping"] = True
    status["scraped_pages"] = 0
    status["remaining_pages"] = 1
    status["current_url"] = page_url
    status["total_characters_scraped"] = 0
    scrape_mode = "single"

    async with AsyncWebCrawler() as crawler:
        data = await process_url(crawler, page_url, status)
        if data:
            # --- DATABASE SAVE (using async wrapper) ---
            await save_scraped_data_wrapper(data, status['user_id'], scrape_mode, status)
            # ---------------------

    # Set final status indicators after completion
    status["scraped_pages"] = 1
    status["remaining_pages"] = 0
    status["is_scraping"] = False

# Function to process each URL during sitemap scraping
async def process_url_with_status(crawler, url, status):
    try:
        new_data = await process_url(crawler, url, status)
        
        if new_data:
            scrape_mode = "sitemap"
            # --- DATABASE SAVE (using async wrapper) ---
            await save_scraped_data_wrapper(new_data, status['user_id'], scrape_mode, status)
            # ---------------------
        
    except Exception as e:
        # process_url handles setting the error in status
        print(f"Error processing {url}: {e}")

# Function to scrape all URLs in a sitemap
async def scrape_sitemap_with_status(sitemap_url, status):
    try:
        sitemap_urls = await get_sitemap_urls(sitemap_url)
        total_urls = len(sitemap_urls)

        if total_urls == 0:
            status["is_scraping"] = False
            status["error"] = "No URLs found in the sitemap."
            return

        status["remaining_pages"] = total_urls
        status["scraped_pages"] = 0
        status["total_characters_scraped"] = 0
        status["is_scraping"] = True

        async with AsyncWebCrawler() as crawler:
            for url in sitemap_urls:
                status["current_url"] = url
                try:
                    await process_url_with_status(crawler, url, status)
                except Exception as e:
                    # process_url_with_status already logs the error, just break the loop
                    break  

                status["scraped_pages"] += 1 # Incremented ONLY here for sitemap mode
                status["remaining_pages"] -= 1

                await asyncio.sleep(1) # Sleep for a short duration to avoid overwhelming the server

        status["is_scraping"] = False
        status["remaining_pages"] = 0
        status["error"] = None
    except Exception as e:
        status["is_scraping"] = False
        status["error"] = f"Error during sitemap scraping: {str(e)}"
        print(f"Error during sitemap scraping: {str(e)}")

# Main scraper runner
async def run_scraper(scrape_mode, scrape_url, status):
    if scrape_mode == "single":
        await scrape_single_page_with_status(scrape_url, status)
    elif scrape_mode == "sitemap":
        await scrape_sitemap_with_status(scrape_url, status)
    else:
        status["is_scraping"] = False
        status["error"] = "Invalid scrape mode. Please choose 'single' or 'sitemap'."
    
    # Ensure status is definitely set to false when the runner exits
    status["is_scraping"] = False

# Threaded function to run the scraper in the background
def run_scraper_thread(scrape_mode, scrape_url, status):
    # This thread runs the entire async event loop
    asyncio.run(run_scraper(scrape_mode, scrape_url, status))

# API endpoint to start the scraper
@csrf_exempt
def api_scrape(request):
    if request.method == "POST":
        try:
            payload = json.loads(request.body)
            scrape_url = payload.get("scrape_url")
            scrape_mode = payload.get("scrape_mode")
            user_id = payload.get("user_id")
            rem_link = payload.get("rem_link")

            if not scrape_url or not scrape_mode or not user_id:
                return JsonResponse({"error": "Missing required parameters: 'scrape_url', 'scrape_mode', or 'user_id'."}, status=400)

            if rem_link is None or not isinstance(rem_link, int) or rem_link <= 0:
                # The single-page scrape handles this logic, but we should prevent starting here too
                # if the user has 0 links remaining.
                return JsonResponse({"error": "Invalid or missing 'rem_link' parameter."}, status=400)

            # If a task is already running, prevent starting a new one
            if user_id in scraping_status and scraping_status[user_id]["status"].get("is_scraping", False):
                 return JsonResponse({"error": "A scraping task is already running for this user."}, status=409)

            status = {
                "scraped_pages": 0,
                "remaining_pages": 0,
                "current_url": None,
                "total_characters_scraped": 0,
                "is_scraping": True,
                "user_id": user_id,
                "file_size": 0, # Kept for status response compatibility, though no longer relevant
                "rem_link": rem_link,
                "error": None,
            }

            scraping_status[user_id] = {"url": scrape_url, "mode": scrape_mode, "status": status}
            thread = threading.Thread(target=run_scraper_thread, args=(scrape_mode, scrape_url, status))
            thread.start()

            return JsonResponse({"status": "Scrape started", "scrape_url": scrape_url, "scrape_mode": scrape_mode})

        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON format in the request body."}, status=400)

    return JsonResponse({"error": "Invalid request method. Only POST requests are allowed."}, status=405)

# Get scrape status
def get_scrape_status(request, user_id):
    entry = scraping_status.get(user_id)
    if not entry:
        # Change 404 to 200 with an empty/completed status to prevent the frontend from erroring/spamming the console
        return JsonResponse({"user_id": user_id, "is_scraping": False, "error": "No scraping task found for this user_id.", "scraped_pages": 0, "remaining_pages": 0}, status=200)

    status = entry.get("status", {})
    all_urls = [status.get("current_url") or entry.get("url")]
    response_data = {
        "user_id": user_id,
        "url": entry.get("url"),
        "mode": entry.get("mode"),
        "scraped_pages": status.get("scraped_pages", 0),
        "total_characters_scraped": status.get("total_characters_scraped", 0),
        "is_scraping": status.get("is_scraping", False),
        "remaining_pages": status.get("remaining_pages", 0),
        "current_url": status.get("current_url") or entry.get("url"),
        "file_size": status.get("file_size", 0),
        "all_urls": all_urls,
        "error": status.get("error", ""),
    }
    return JsonResponse(response_data)

# NOTE: The old append_data_to_file function has been removed.

# Django view for scrape page
def scrape(request):
    # This view is for rendering the HTML template
    return render(request, 'index.html')
