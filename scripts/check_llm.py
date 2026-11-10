"""Diagnose Groq problems in 3 small steps. Prints the full, untruncated error.

  python scripts/check_llm.py
  python scripts/check_llm.py --model some-other-model

Step 1  lists the models your key can use (catches a retired model name).
Step 2  makes a plain chat call (catches a bad key or a bad model name).
Step 3  makes the structured triage call the pipeline uses (catches
        structured-output / tool-calling problems).
"""
import argparse
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.config import get_settings  # noqa: E402
from app.prompts import TRIAGE_SYSTEM  # noqa: E402
from app.schemas import TriageOutput  # noqa: E402


def show_error(e: Exception) -> None:
    print(f"   FAILED: {type(e).__name__}")
    print("   " + str(e).replace("\n", "\n   "))
    cause = e.__cause__ or e.__context__
    if cause:
        print(f"   caused by {type(cause).__name__}: {cause}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", help="override LLM_MODEL")
    args = ap.parse_args()

    s = get_settings()
    model = args.model or s.llm_model
    if not s.groq_api_key:
        print("GROQ_API_KEY is not set. Put it in .env at the project root.")
        return
    print(f"Model: {model}   key: {s.groq_api_key[:4]}...{s.groq_api_key[-4:]} ({len(s.groq_api_key)} chars)\n")

    print("Step 1: models available to your key")
    try:
        from groq import Groq

        ids = sorted(m.id for m in Groq(api_key=s.groq_api_key).models.list().data)
        for i in ids:
            print(("   * " if i == model else "     ") + i)
        if model not in ids:
            print(f"   !! '{model}' is NOT in this list. Set LLM_MODEL to one of the names above.")
    except Exception as e:  # noqa: BLE001
        show_error(e)

    from langchain_groq import ChatGroq

    chat = ChatGroq(model=model, api_key=s.groq_api_key, temperature=0)

    print("\nStep 2: plain chat call")
    try:
        print("   OK:", chat.invoke("Reply with the single word: ok").content.strip()[:80])
    except Exception as e:  # noqa: BLE001
        show_error(e)

    print("\nStep 3: structured triage call (what the pipeline uses)")
    try:
        out = chat.with_structured_output(TriageOutput).invoke(
            [("system", TRIAGE_SYSTEM),
             ("human", "<ticket>\nI was charged twice for my October subscription.\n</ticket>")]
        )
        print("   OK:", out)
    except Exception as e:  # noqa: BLE001
        show_error(e)
        if "--trace" in sys.argv:
            traceback.print_exc()


if __name__ == "__main__":
    main()
