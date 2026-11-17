import os
from dotenv import load_dotenv
from src.rag import answer_question

load_dotenv()

# 20 automated test queries covering roles, architecture, tech stack, and security
TEST_QUERIES = [
    "hello",
    "who is phat role in this",
    "group 7",
    "RAG",
    "project team",
    "Team, Roles and Stakeholders",
    "vbi",
    "Katalon",
    "role",
    "What is the system architecture?",
    "Explain the security model",
    "Confluence integration details",
    "What database is used?",
    - "Supabase pgvector configuration",
    "Gemini model fallback strategy",
    "DACI framework definition",
    "Prompt injection safety fixture",
    "Roadmap and workstream progress",
    "What are the deployment platforms?",
    "Summarize project deliverables",
]

def run_tests():
    test_email = "hoanglunhat31@gmail.com"
    print(f"🚀 Running 20 automated test queries for user: {test_email}\n" + "="*50)
    
    for i, query in enumerate(TEST_QUERIES, start=1):
        print(f"\n[Test {i}/20] Query: '{query}'")
        try:
            result = answer_question(query, user_email=test_email)
            print(f"Answer: {result.get('answer', '')[:200]}...")
            sources = [s.get('title') for s in result.get('sources', [])]
            print(f"Sources found: {len(sources)} -> {sources[:2]}")
        except Exception as e:
            print(f"❌ Error: {e}")
        print("-" * 50)

if __name__ == "__main__":
    run_tests()