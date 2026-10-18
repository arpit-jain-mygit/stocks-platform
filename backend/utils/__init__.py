"""
utils - shared helpers (IDs, page cache, Gemini).

Loads the local .env file as soon as anything from utils is imported, so every
helper sees GEMINI_API_KEY, GEMINI_VISION_MODEL, PAGE_CACHE_DIR etc. no matter
which one is imported first. On Railway the variables come from the dashboard
instead, and load_dotenv() simply finds no file and does nothing.
"""
from dotenv import load_dotenv

load_dotenv()
