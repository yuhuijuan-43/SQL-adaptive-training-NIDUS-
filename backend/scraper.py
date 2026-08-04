import requests
from bs4 import BeautifulSoup
import sqlite3
import re
import json
import os
from db import get_connection, DB_PATH
from seeding import seed_questions

SCRAPED_SOURCES = {
    "w3resource_sql": "https://www.w3resource.com/sql-exercises/"
}

def scrape_w3resource_sql():
    print("Attempting to scrape w3resource SQL exercises...")
    questions = []
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        resp = requests.get(SCRAPED_SOURCES["w3resource_sql"], headers=headers, timeout=15)
        if resp.status_code != 200:
            print(f"Failed to access w3resource, status: {resp.status_code}")
            return questions
        soup = BeautifulSoup(resp.text, 'lxml')
        print(f"Page title: {soup.title.string if soup.title else 'N/A'}")
        links = soup.select('a[href*="sql-exercises"]')
        for link in links:
            href = link.get('href', '')
            if href and 'exercises' in href and href not in ['/sql-exercises/']:
                print(f"  Found link: {href} - {link.text.strip()}")
    except Exception as e:
        print(f"Scraping error: {e}")
    return questions

def scrape_and_store():
    scraped = scrape_w3resource_sql()
    print(f"Scraped {len(scraped)} questions from w3resource")
    seed_questions()
    conn = get_connection()
    count = conn.execute('SELECT COUNT(*) FROM questions').fetchone()[0]
    conn.close()
    print(f"Total questions in database: {count}")

if __name__ == '__main__':
    scrape_and_store()