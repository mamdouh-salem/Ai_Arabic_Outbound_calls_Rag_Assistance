from dotenv import load_dotenv
load_dotenv()

from langsmith import traceable
from langchain_core.tracers.langchain import wait_for_all_tracers

@traceable(name="minimal-test")
def hello():
    return "hi"

result = hello()
print(f"Function returned: {result}")

wait_for_all_tracers()
print("Flushed. Now run check_langsmith_v2.py again.")
