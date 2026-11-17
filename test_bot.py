import os
from dotenv import load_dotenv
from src.rag import answer_question

# Explicitly load .env file from root
load_dotenv()

# Verify API key is loaded
api_key = os.getenv("SLACK_API_KEY") or os.getenv("GEMINI_API_KEY")
print(f"🔑 Gemini/Slack API Key Loaded: {'YES (starts with ' + api_key[:6] + '...' if api_key else 'NO ❌'}")

# 20 test queries tailored to your actual Confluence workspace titles
TEST_QUERIES = [
    "hello",
    "What is in Workspace Governance?",
    "Project Charter and Scope",
    "Team, Roles and Stakeholders",
    "Project Planning and Progress",
    "Meetings and Communication",
    "Research and Literature",
    "Requirements and Knowledge Sources",
    "Architecture and Technical Design",
    "Development and Integrations",
    "Testing and Model Evaluation",
    "Risks, Decisions and Change Control",
    "Risk Register and Change Log",
    "Deliverables, Review and Handover",
    "Templates and Atlassian Resources",
    "What are our project roles?",
    "Explain the architecture design",
    "What is our testing and model evaluation plan?",
    "Show me the risk register details",
    "Summarize project deliverables",
]

def run_tests():
    test_email = "105234956@student.swin.edu.au"
    print(f"🚀 Running 20 Confluence-aligned test queries for user: {test_email}\n" + "="*50)
    
    for i, query in enumerate(TEST_QUERIES, start=1):
        print(f"\n[Test {i}/20] Query: '{query}'")
        try:
            result = answer_question(query, user_email=test_email)
            print(f"Answer: {result.get('answer', '')}")
            sources = [s.get('title') for s in result.get('sources', [])]
            print(f"Sources found: {len(sources)} -> {sources}")
        except Exception as e:
            print(f"❌ Error: {e}")
        print("-" * 50)

if __name__ == "__main__":
    run_tests()