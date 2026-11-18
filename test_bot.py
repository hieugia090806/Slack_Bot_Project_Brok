import os
from dotenv import load_dotenv
from src.rag import answer_question

# Explicitly load .env file from root
load_dotenv()

# Verify API key is loaded
api_key = os.getenv("SLACK_API_KEY") or os.getenv("GEMINI_API_KEY")
print(
    f"🔑 Gemini/Slack API Key Loaded: "
    f"{'YES (starts with ' + api_key[:6] + '...' if api_key else 'NO ❌'}"
)

TEST_QUERIES = [
    "Who is the mentor",
    "What is in Workspace Governance?",
    "Project Charter and Scope",
    "Team, Roles and Stakeholders",
    "Project Planning and Progress",
    "Meetings and Communication",
    "Research and Literature",
    "Requirements and Knowledge Sources",
    "Architecture and Technical Design",
    "Development and Integrations",
]


def run_tests():
    test_email = "105234956@student.swin.edu.au"

    passed = 0
    failed = 0
    failed_cases = []

    print(
        f"🚀 Running {len(TEST_QUERIES)} Confluence-aligned test queries "
        f"for user: {test_email}\n"
        + "=" * 60
    )

    for i, query in enumerate(TEST_QUERIES, start=1):
        print(f"\n[Test {i}/{len(TEST_QUERIES)}] Query: '{query}'")

        try:
            result = answer_question(query, user_email=test_email)

            answer = result.get("answer", "")
            sources = [s.get("title") for s in result.get("sources", [])]

            print(f"Answer: {answer}")
            print(f"Sources found: {len(sources)} -> {sources}")

            # PASS criteria
            if answer and len(sources) > 0:
                passed += 1
                print("✅ PASS")
            else:
                failed += 1
                failed_cases.append(query)
                print("❌ FAIL (No answer or no sources)")

        except Exception as e:
            failed += 1
            failed_cases.append(query)

            print(f"❌ ERROR: {e}")
            print("❌ FAIL")

        print("-" * 60)

    total = len(TEST_QUERIES)
    success_rate = (passed / total) * 100 if total else 0

    print("\n" + "=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)
    print(f"Total Tests : {total}")
    print(f"✅ Passed   : {passed}")
    print(f"❌ Failed   : {failed}")
    print(f"📈 Success  : {success_rate:.2f}%")

    if failed_cases:
        print("\nFailed Queries:")
        for idx, query in enumerate(failed_cases, start=1):
            print(f"{idx}. {query}")

    print("=" * 60)


if __name__ == "__main__":
    run_tests()